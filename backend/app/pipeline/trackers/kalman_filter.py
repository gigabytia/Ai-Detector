import numpy as np
from filterpy.kalman import KalmanFilter

def tlwh_to_xyah(tlwh):
    x, y, w, h = tlwh
    cx = x + w / 2.0
    cy = y + h / 2.0
    a = w / max(1e-6, h)
    return np.array([cx, cy, a, h], dtype=np.float32)

def xyah_to_tlwh(xyah):
    cx, cy, a, h = xyah
    w = a * h
    x = cx - w / 2.0
    y = cy - h / 2.0
    return np.array([x, y, w, h], dtype=np.float32)

class KalmanXYAH:
    """
    Простая KF для ByteTrack: состояние (cx,cy,a,h, vx,vy,va,vh)
    """
    def __init__(self):
        self.kf = KalmanFilter(dim_x=8, dim_z=4)
        self.kf.F = np.eye(8, dtype=np.float32)
        for i in range(4):
            self.kf.F[i, i+4] = 1.0

        self.kf.H = np.zeros((4, 8), dtype=np.float32)
        self.kf.H[0,0] = 1.0
        self.kf.H[1,1] = 1.0
        self.kf.H[2,2] = 1.0
        self.kf.H[3,3] = 1.0

        self.kf.P *= 10.0
        self.kf.R *= 1.0
        self.kf.Q *= 0.01

    def initiate(self, xyah: np.ndarray):
        self.kf.x[:4] = xyah.reshape(4,1)
        self.kf.x[4:] = 0.0

    def predict(self):
        self.kf.predict()

    def update(self, xyah: np.ndarray):
        self.kf.update(xyah.reshape(4,1))

    @property
    def mean(self) -> np.ndarray:
        return self.kf.x.reshape(-1).astype(np.float32)