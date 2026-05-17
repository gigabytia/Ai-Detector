import numpy as np
from ..config import SETTINGS

def get_angle(a, b, c) -> float:
    ba = a - b
    bc = c - b
    dot = float(np.dot(ba, bc))
    mba = float(np.linalg.norm(ba))
    mbc = float(np.linalg.norm(bc))
    if mba == 0 or mbc == 0:
        return 180.0
    cosv = np.clip(dot / (mba * mbc), -1.0, 1.0)
    return float(np.degrees(np.arccos(cosv)))

def classify_pose_static(keypoints_xy: np.ndarray, confidences: np.ndarray, bbox_xyxy: np.ndarray) -> str:
    thr = SETTINGS.KP_POSE_THR
    pose = "unknown"

    x1, y1, x2, y2 = map(float, bbox_xyxy)
    bw = max(1.0, x2 - x1)
    bh = max(1.0, y2 - y1)
    aspect = bw / bh

    if int(np.sum(confidences > thr)) >= 5:
        pose = "standing"

    sitting_score = 0
    if all(confidences[i] > thr for i in [11, 13, 15]):
        ang = get_angle(keypoints_xy[11], keypoints_xy[13], keypoints_xy[15])
        if 50 < ang < 130:
            sitting_score += 1

    if all(confidences[i] > thr for i in [12, 14, 16]):
        ang = get_angle(keypoints_xy[12], keypoints_xy[14], keypoints_xy[16])
        if 50 < ang < 130:
            sitting_score += 1

    if sitting_score >= 1:
        pose = "sitting"

    if aspect > 1.35:
        pose = "lying"

    return pose

def check_hand_raised(keypoints_xy: np.ndarray, confidences: np.ndarray, bbox_xyxy: np.ndarray, currently_raised: bool) -> bool:
    """
    Более строгая эвристика поднятой руки (меньше false positives):
    - отдельный порог уверенности HAND_KP_THR
    - wrist выше shoulder на margin
    - рука направлена "вверх" (dy > 0 и dy относительно dx достаточно большое)
    - если есть голова (nose/eyes/ears) — wrist должен быть примерно на уровне головы или выше
    """
    thr = float(SETTINGS.HAND_KP_THR)

    x1, y1, x2, y2 = map(float, bbox_xyxy)
    bh = float(max(1.0, y2 - y1))

    enter_margin = SETTINGS.HAND_RAISE_ENTER_RATIO * bh
    exit_margin  = SETTINGS.HAND_RAISE_EXIT_RATIO  * bh
    margin = exit_margin if currently_raised else enter_margin

    chain = SETTINGS.HAND_RAISE_CHAIN_RATIO * bh

    # ----- helper: head level (если доступно) -----
    # COCO: 0 nose, 1 left_eye, 2 right_eye, 3 left_ear, 4 right_ear
    head_idxs = [0, 1, 2, 3, 4]
    head_ys = [float(keypoints_xy[i][1]) for i in head_idxs if float(confidences[i]) > thr]
    head_y = min(head_ys) if head_ys else None  # чем меньше y, тем выше

    # Допуск: wrist может быть чуть ниже верхней точки головы, но не на уровне груди
    head_allow = 0.22 * bh  # можно подстроить (0.18..0.28)

    def arm_up(wrist_i: int, elbow_i: int, shoulder_i: int) -> bool:
        cw = float(confidences[wrist_i])
        ce = float(confidences[elbow_i])
        cs = float(confidences[shoulder_i])

        if cw <= thr or cs <= thr:
            return False

        wx, wy = map(float, keypoints_xy[wrist_i])
        sx, sy = map(float, keypoints_xy[shoulder_i])

        # 1) wrist выше shoulder на margin
        if not (wy < sy - margin):
            return False

        # 2) Рука должна быть направлена вверх (а не в сторону/вперёд):
        # dy = sy - wy (положительный если вверх), dx = |wx-sx|
        dy = sy - wy
        dx = abs(wx - sx) + 1e-6
        # если dy маленький относительно dx — это чаще "рука в сторону"
        if (dy / dx) < 0.8:
            return False

        # 3) Если есть голова — требуем wrist примерно на уровне головы
        if head_y is not None:
            if not (wy < head_y + head_allow):
                return False

        # 4) Усиливаем уверенность цепочкой, если доступны elbow+wrist:
        if ce > thr:
            ex, ey = map(float, keypoints_xy[elbow_i])
            # elbow выше shoulder и wrist выше elbow
            if (ey < sy - chain) and (wy < ey - chain * 0.5):
                return True

        # Если elbow не уверенный — всё равно допускаем поднятую руку,
        # но только при прохождении строгих условий 1-3 выше.
        return True

    # right arm: shoulder=6 elbow=8 wrist=10
    if arm_up(10, 8, 6):
        return True

    # left arm: shoulder=5 elbow=7 wrist=9
    if arm_up(9, 7, 5):
        return True

    return False