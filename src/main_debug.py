import argparse, os, time
import cv2, numpy as np, yaml

from utils import now_ts, ensure_dir, Timer, write_csv_header, append_csv
from orb_detector import (build_orb, build_flann_lsh, preprocess, detect_and_compute,
                          ratio_test, project_bbox, draw_overlay)
from tracker_utils import (create_tracker, rect_from_quad, quad_from_rect, EMASmoother)

# ==== Fungsi bantu untuk resize dan posisi window ====
def resize_for_display(img, scale=0.5, max_width=800, max_height=600):
    h, w = img.shape[:2]
    ratio = min(max_width / w, max_height / h, scale)
    if ratio < 1:
        img = cv2.resize(img, (int(w * ratio), int(h * ratio)))
    return img

def load_config(path):
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def set_camera_size(cap, w, h):
    if w and h:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(w))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(h))

def bbox_from_matches(matches, ref_kp, kp_frame, ref_img_shape, cfg):
    src_pts = np.float32([ref_kp[m.queryIdx].pt for m in matches]).reshape(-1,1,2)
    dst_pts = np.float32([kp_frame[m.trainIdx].pt for m in matches]).reshape(-1,1,2)
    H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, cfg['homography']['ransac_reproj_threshold'])
    if H is None or mask is None: return None, 0
    inliers = int(mask.ravel().sum())
    if inliers < cfg['homography']['min_inliers']: return None, inliers
    bbox = project_bbox(ref_img_shape, H)
    rect = rect_from_quad(bbox)
    return rect, inliers

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--video', default=None)
    ap.add_argument('--webcam', type=int, default=None)
    ap.add_argument('--debug', action='store_true', help='Tampilkan hasil setiap tahap proses')
    args = ap.parse_args()

    cfg = load_config(args.config)
    orb = build_orb(**cfg['detector'])
    matcher = build_flann_lsh(cfg['matcher']['index_params'], cfg['matcher']['search_params'])
    debug = args.debug

    # load refs
    ref_imgs, ref_kps, ref_dess = [], [], []
    for ref_path in cfg['io']['reference_images']:
        assert os.path.exists(ref_path), f'Ref not found: {ref_path}'
        ref_img = cv2.imread(ref_path)
        ref_gray = preprocess(ref_img, cfg['detection']['blur_kernel'])
        kp, des = detect_and_compute(orb, ref_gray)
        if des is None or len(kp)==0:
            print('[WARN] no kp in', ref_path); continue
        ref_imgs.append(ref_img); ref_kps.append(kp); ref_dess.append(des)
    assert len(ref_imgs)>0, 'No refs.'

    if args.video:
        cap = cv2.VideoCapture(args.video)
    else:
        cap = cv2.VideoCapture(0 if args.webcam is None else args.webcam)
    assert cap.isOpened(), 'Cannot open source'
    set_camera_size(cap, cfg['detection'].get('resize_width',320), cfg['detection'].get('resize_height',240))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    ensure_dir(cfg['io']['log_dir'])
    ts = now_ts(); log_path = os.path.join(cfg['io']['log_dir'], f'log_{ts}.csv')
    write_csv_header(log_path, ['frame','id','cx','cy','x','y','w','h','proc_ms'])

    trackers = []
    next_id = 0

    vw = None
    if cfg['visual']['write_video']:
        vw = cv2.VideoWriter(cfg['visual']['output_video_path'], cv2.VideoWriter_fourcc(*'XVID'),
                             cfg['visual']['output_fps'], (width, height))

    frame_idx = 0; t0 = time.perf_counter()

    while True:
        ret, frame = cap.read()
        if not ret: break

        frame_logs = []

        with Timer() as t:
            display_info = []
            need_detect = (frame_idx % max(1, cfg['tracking']['redetect_interval']) == 0) or len(trackers) < 1

            if debug:
                show1 = resize_for_display(frame, 0.4)
                cv2.imshow("1. Original Frame", show1)
                
            if need_detect:
                gray = preprocess(frame, cfg['detection']['blur_kernel'])
                if debug:
                    show2 = resize_for_display(gray, 0.4)
                    cv2.imshow("2. Preprocessed (Gray+Blur)", show2)
                    
                kp_frame, des_frame = detect_and_compute(orb, gray)
                if debug and des_frame is not None:
                    dbg_kp = cv2.drawKeypoints(gray, kp_frame, None, color=(0,255,0))
                    show3 = resize_for_display(dbg_kp, 0.4)
                    cv2.imshow("3. ORB Keypoints", show3)
                    
                if des_frame is not None and len(kp_frame)>0:
                    for r_img, r_kp, r_des in zip(ref_imgs, ref_kps, ref_dess):
                        try:
                            matches = matcher.knnMatch(r_des, des_frame, k=cfg['matcher']['knn_k'])
                        except:
                            matches = matcher.knnMatch(r_des.astype('float32'), des_frame.astype('float32'), k=cfg['matcher']['knn_k'])
                        good = ratio_test(matches, cfg['matcher']['ratio'])
                        if len(good) < cfg['detection']['min_good_matches']: continue

                        if debug:
                            dbg_match = cv2.drawMatches(r_img, r_kp, frame, kp_frame, good, None,
                                                        flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
                            show4 = resize_for_display(dbg_match, 0.5, max_width=900)
                            cv2.imshow("4. Good Matches", show4)
                            
                        rect, inliers = bbox_from_matches(good, r_kp, kp_frame, r_img.shape, cfg)
                        if rect is None: continue
                        x, y, w, h = rect
                        if w < cfg['filter']['min_width'] or h < cfg['filter']['min_height']:
                            continue
                        if w > cfg['filter']['max_width'] or h > cfg['filter']['max_height']:
                            continue

                        if debug:
                            dbg_rect = frame.copy()
                            cv2.rectangle(dbg_rect, (x,y), (x+w,y+h), (0,255,0), 2)
                            show5 = resize_for_display(dbg_rect, 0.4)
                            cv2.imshow("5. Bounding Box (Detected)", show5)
                            
                        if len(trackers) == 0:
                            trk = create_tracker(cfg['tracking']['type'] if cfg['tracking']['enabled'] else 'KCF')
                            trk.init(frame, rect)
                            smoother = EMASmoother(alpha=cfg['tracking']['ema_alpha'])
                            trackers.append({'id': next_id, 'tracker': trk, 'smoother': smoother, 'lost':0, 'rect':rect})
                            next_id += 1
                        else:
                            trackers[0]['rect'] = rect

            # update trackers
            to_remove = []
            for tr in trackers:
                ok, box = tr['tracker'].update(frame)
                if ok:
                    x,y,w,h = [int(v) for v in box]
                    sx, sy, sw, sh = tr['smoother'].update((x,y,w,h))
                    tr['rect'] = (int(round(sx)), int(round(sy)), int(round(sw)), int(round(sh)))
                    tr['lost'] = 0
                    xr, yr, wr, hr = tr['rect']
                    cx, cy = xr + wr//2, yr + hr//2
                    info = {'id': tr['id'], 'cx': cx, 'cy': cy, 'x': xr, 'y': yr, 'w': wr, 'h': hr, 'color': (0,255,0)}
                    display_info.append((quad_from_rect(xr, yr, wr, hr), info))
                    frame_logs.append([frame_idx, tr['id'], cx, cy, xr, yr, wr, hr])
                else:
                    tr['lost'] += 1
                    if tr['lost'] > cfg['tracking']['lost_max']:
                        to_remove.append(tr)
            for tr in to_remove:
                trackers.remove(tr)

        for row in frame_logs:
            row.append(round(t.elapsed,3))
            append_csv(log_path, row)

        fps = (frame_idx+1)/(time.perf_counter()-t0) if frame_idx>0 else 0.0
        overlay = draw_overlay(frame, bbox_pts_list=display_info, show_fps=cfg['visual']['show_fps'], fps=fps,
                               box_size=cfg['visual'].get('fixed_box_size', 250))

        if cfg['visual']['show_window']:
            show_main = resize_for_display(overlay, 0.5)
            cv2.imshow(cfg['visual']['window_name'], show_main)
            
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

        if vw is not None:
            vw.write(overlay)

        frame_idx += 1

    cap.release()
    if vw is not None:
        vw.release()
    cv2.destroyAllWindows()
    print('Log saved to', log_path)

if __name__ == '__main__':
    main()
