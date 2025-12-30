import cv2, numpy as np

def create_tracker(tracker_type="KCF"):
        return cv2.legacy.TrackerKCF_create()

def rect_from_quad(bbox_pts):
    x, y, w, h = cv2.boundingRect(bbox_pts)
    return (x, y, w, h)

def quad_from_rect(x, y, w, h):
    return np.array([[[x,y]], [[x+w,y]], [[x+w,y+h]], [[x,y+h]]])

class EMASmoother:
    def __init__(self, alpha=0.2):
        self.alpha = float(alpha); self.last = None
    def update(self, rect):
        if self.last is None:
            self.last = rect; return rect
        ax = self.alpha
        lx, ly, lw, lh = self.last
        x = ax*rect[0] + (1-ax)*lx
        y = ax*rect[1] + (1-ax)*ly
        w = ax*rect[2] + (1-ax)*lw
        h = ax*rect[3] + (1-ax)*lh
        self.last = (x,y,w,h); return self.last
