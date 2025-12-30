import cv2, numpy as np

def build_orb(n_features, scale_factor, n_levels, fast_threshold,
              edge_threshold, patch_size):
    return cv2.ORB_create(
        nfeatures=n_features,
        scaleFactor=scale_factor,
        nlevels=n_levels,
        fastThreshold=fast_threshold,
        edgeThreshold=edge_threshold,
        patchSize=patch_size
    )

def build_flann_lsh(index_params, search_params):
    return cv2.FlannBasedMatcher(index_params, search_params)

def preprocess(img, blur_kernel=3):
    if blur_kernel and blur_kernel > 0 and blur_kernel % 2 == 1:
        img = cv2.GaussianBlur(img, (blur_kernel, blur_kernel), 0)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return gray

def detect_and_compute(orb, img_gray):
    return orb.detectAndCompute(img_gray, None)

def ratio_test(matches, ratio=0.75):
    good = []
    for m_n in matches:
        if len(m_n) != 2:
            continue
        m, n = m_n
        if m.distance < ratio * n.distance:
            good.append(m)
    return good

def project_bbox(ref_shape, H):
    h, w = ref_shape[:2]
    pts = np.float32([[0,0],[w,0],[w,h],[0,h]]).reshape(-1,1,2)
    dst = cv2.perspectiveTransform(pts, H)
    return dst

def draw_overlay(frame, bbox_pts_list=None, show_fps=True, fps=None, box_size=250, debug_lines=None):
    """
    debug_lines: list of strings, shown at top-left of frame (one per line)
    bbox_pts_list: list of tuples (quad_pts, info_dict)
    """
    out = frame.copy()
    if bbox_pts_list:
        for _, info in bbox_pts_list:
            # Ambil centroid
            cx, cy = int(info['cx']), int(info['cy'])

            # Hitung bounding box fixed-size mengelilingi centroid
            half = box_size // 2
            x1, y1 = cx - half, cy - half
            x2, y2 = cx + half, cy + half

            # Gambar kotak hijau tetap
            cv2.rectangle(out, (x1, y1), (x2, y2), info.get('color', (0,255,0)), 2)

            # Gambar titik centroid merah
            cv2.circle(out, (cx, cy), 7, (0,0,255), -1)

            # Tulis ID + koordinat
            cv2.putText(out, f"ID:{info.get('id','?')} ({cx},{cy})",
                        (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (255,255,255), 1, cv2.LINE_AA)

    # Debug lines (tampilkan di kiri atas)
    if debug_lines:
        x = 10
        y = 50
        line_h = 18
        for i, line in enumerate(debug_lines):
            yy = y + i * line_h
            cv2.putText(out, line, (x, yy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (0,255,255), 1, cv2.LINE_AA)

    if show_fps and fps is not None:
        cv2.putText(out, f"FPS: {fps:.1f}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255,255,255), 2, cv2.LINE_AA)

    return out
