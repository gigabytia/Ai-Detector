"""
Классификатор поз на основе ключевых точек YOLOv8-pose.
Определяет три позы: стоит, сидит, поднята рука.
"""
import numpy as np
from typing import Tuple, List, Optional, Dict
from config import PoseConfig


class PoseClassifier:
    """
    Классифицирует позу человека по 17 ключевым точкам COCO.

    Позы:
        - "standing"    — человек стоит
        - "sitting"     — человек сидит
        - "hand_raised" — поднята хотя бы одна рука
        - "unknown"     — не удалось определить
    """

    def __init__(self, config: PoseConfig = None):
        self.config = config or PoseConfig()
        # История поз для сглаживания (track_id -> список последних поз)
        self._pose_history: Dict[int, List[str]] = {}
        self._history_length = 5  # Сколько кадров учитывать для сглаживания

    def classify(
        self,
        keypoints: np.ndarray,
        confidences: np.ndarray,
        track_id: Optional[int] = None,
        bbox: Optional[Tuple[float, float, float, float]] = None,
    ) -> Tuple[str, Dict[str, float]]:
        """
        Классифицирует позу по ключевым точкам.

        Args:
            keypoints:    массив (17, 2) — координаты x, y
            confidences:  массив (17,) — уверенности каждой точки
            track_id:     ID трека для сглаживания по времени
            bbox:         (x1, y1, x2, y2) bounding box

        Returns:
            (pose_label, scores_dict)
            pose_label — строка: "standing", "sitting", "hand_raised", "unknown"
            scores_dict — словарь уверенностей для каждой позы
        """
        scores = {
            "standing": 0.0,
            "sitting": 0.0,
            "hand_raised": 0.0,
        }

        conf_thr = self.config.KEYPOINT_CONFIDENCE_THRESHOLD

        # ── Проверка поднятой руки ──────────────────────────
        hand_raised = self._check_hand_raised(keypoints, confidences, conf_thr)
        if hand_raised:
            scores["hand_raised"] = 1.0

        # ── Определение стоит/сидит ─────────────────────────
        body_pose = self._classify_body_pose(keypoints, confidences, conf_thr, bbox)
        if body_pose == "sitting":
            scores["sitting"] = 1.0
        elif body_pose == "standing":
            scores["standing"] = 1.0

        # ── Выбор итоговой позы (приоритет: рука > сидит/стоит) ──
        # Поднятая рука может сочетаться со стоя/сидя,
        # но мы выделяем её как отдельное состояние
        if scores["hand_raised"] > 0.5:
            pose = "hand_raised"
        elif scores["sitting"] > scores["standing"]:
            pose = "sitting"
        elif scores["standing"] > 0:
            pose = "standing"
        else:
            pose = "unknown"

        # ── Сглаживание по времени ──────────────────────────
        if track_id is not None:
            pose = self._smooth_pose(track_id, pose)

        return pose, scores

    def classify_multiple(
        self,
        all_keypoints: np.ndarray,
        all_confidences: np.ndarray,
        track_ids: Optional[List[int]] = None,
        bboxes: Optional[np.ndarray] = None,
    ) -> List[Tuple[str, Dict[str, float]]]:
        """
        Классифицирует позы для нескольких людей.

        Args:
            all_keypoints:    (N, 17, 2)
            all_confidences:  (N, 17)
            track_ids:        список из N id-шек (или None)
            bboxes:           (N, 4) или None

        Returns:
            Список из N кортежей (pose_label, scores)
        """
        results = []
        n = all_keypoints.shape[0]

        for i in range(n):
            tid = track_ids[i] if track_ids is not None else None
            bb = tuple(bboxes[i]) if bboxes is not None else None
            pose, scores = self.classify(
                all_keypoints[i], all_confidences[i], tid, bb
            )
            results.append((pose, scores))

        return results

    # ================================================================
    #  Приватные методы
    # ================================================================

    def _check_hand_raised(
        self,
        kp: np.ndarray,
        conf: np.ndarray,
        thr: float,
    ) -> bool:
        """Проверяет, поднята ли хотя бы одна рука выше плеча."""
        left_wrist = kp[9]
        right_wrist = kp[10]
        left_shoulder = kp[5]
        right_shoulder = kp[6]
        left_elbow = kp[7]
        right_elbow = kp[8]
        nose = kp[0]

        offset = self.config.RAISED_HAND_OFFSET

        # Левая рука поднята
        if conf[9] > thr and conf[5] > thr:
            # Запястье выше плеча (Y уменьшается вверх)
            if left_wrist[1] < left_shoulder[1] - offset:
                return True

        # Правая рука поднята
        if conf[10] > thr and conf[6] > thr:
            if right_wrist[1] < right_shoulder[1] - offset:
                return True

        # Дополнительная проверка: локоть выше плеча + запястье выше локтя
        if conf[7] > thr and conf[5] > thr and conf[9] > thr:
            if left_elbow[1] < left_shoulder[1] and left_wrist[1] < left_elbow[1]:
                return True

        if conf[8] > thr and conf[6] > thr and conf[10] > thr:
            if right_elbow[1] < right_shoulder[1] and right_wrist[1] < right_elbow[1]:
                return True

        return False

    def _classify_body_pose(
        self,
        kp: np.ndarray,
        conf: np.ndarray,
        thr: float,
        bbox: Optional[Tuple[float, float, float, float]] = None,
    ) -> str:
        """Определяет, стоит человек или сидит."""

        # Ключевые точки
        left_shoulder = kp[5]
        right_shoulder = kp[6]
        left_hip = kp[11]
        right_hip = kp[12]
        left_knee = kp[13]
        right_knee = kp[14]
        left_ankle = kp[15]
        right_ankle = kp[16]

        # ── Метод 1: Угол в колене ──────────────────────────
        knee_angle_sitting = False

        # Левое колено
        if all(conf[i] > thr for i in [11, 13, 15]):
            angle_left = self._calculate_angle(left_hip, left_knee, left_ankle)
            if (self.config.SITTING_KNEE_ANGLE_MIN < angle_left
                    < self.config.SITTING_KNEE_ANGLE_MAX):
                knee_angle_sitting = True

        # Правое колено
        if all(conf[i] > thr for i in [12, 14, 16]):
            angle_right = self._calculate_angle(right_hip, right_knee, right_ankle)
            if (self.config.SITTING_KNEE_ANGLE_MIN < angle_right
                    < self.config.SITTING_KNEE_ANGLE_MAX):
                knee_angle_sitting = True

        # ── Метод 2: Соотношение высот (бёдра vs колени) ────
        ratio_sitting = False

        if (conf[11] > thr and conf[12] > thr
                and conf[13] > thr and conf[14] > thr):
            mid_hip_y = (left_hip[1] + right_hip[1]) / 2
            mid_knee_y = (left_knee[1] + right_knee[1]) / 2
            mid_shoulder_y = 0.0

            if conf[5] > thr and conf[6] > thr:
                mid_shoulder_y = (left_shoulder[1] + right_shoulder[1]) / 2
                torso_length = abs(mid_hip_y - mid_shoulder_y)

                if torso_length > 0:
                    hip_knee_diff = abs(mid_hip_y - mid_knee_y)
                    ratio = hip_knee_diff / torso_length

                    if ratio < self.config.SITTING_HIP_KNEE_RATIO:
                        ratio_sitting = True

        # ── Метод 3: Пропорции в bbox ──────────────────────
        bbox_sitting = False

        if bbox is not None and conf[5] > thr and conf[6] > thr:
            x1, y1, x2, y2 = bbox
            bbox_height = y2 - y1
            bbox_width = x2 - x1

            if bbox_height > 0:
                aspect_ratio = bbox_width / bbox_height
                # У сидящего человека bbox более "квадратный"
                if aspect_ratio > 0.75:
                    bbox_sitting = True

                # Также: ноги занимают малую часть bbox
                if conf[15] > thr and conf[16] > thr:
                    mid_ankle_y = (left_ankle[1] + right_ankle[1]) / 2
                    mid_shoulder_y = (left_shoulder[1] + right_shoulder[1]) / 2
                    leg_portion = (mid_ankle_y - (left_hip[1] + right_hip[1]) / 2) / bbox_height
                    if leg_portion < 0.25:
                        bbox_sitting = True

        # ── Комбинируем методы ──────────────────────────────
        sitting_votes = sum([knee_angle_sitting, ratio_sitting, bbox_sitting])

        if sitting_votes >= 2:
            return "sitting"
        elif sitting_votes == 1 and not self._is_clearly_standing(kp, conf, thr):
            return "sitting"

        # Проверяем "стоит"
        if self._is_clearly_standing(kp, conf, thr):
            return "standing"

        # По умолчанию — стоит (если видим человека)
        visible_count = np.sum(conf > thr)
        if visible_count >= 5:
            return "standing"

        return "unknown"

    def _is_clearly_standing(
        self,
        kp: np.ndarray,
        conf: np.ndarray,
        thr: float,
    ) -> bool:
        """Проверяет, явно ли человек стоит."""
        left_hip = kp[11]
        right_hip = kp[12]
        left_knee = kp[13]
        right_knee = kp[14]
        left_ankle = kp[15]
        right_ankle = kp[16]
        left_shoulder = kp[5]
        right_shoulder = kp[6]

        # Ноги должны быть вытянуты (большой угол в колене)
        if all(conf[i] > thr for i in [11, 13, 15]):
            angle = self._calculate_angle(left_hip, left_knee, left_ankle)
            if angle > 150:
                return True

        if all(conf[i] > thr for i in [12, 14, 16]):
            angle = self._calculate_angle(right_hip, right_knee, right_ankle)
            if angle > 150:
                return True

        # Бёдра значительно выше колен, колени выше лодыжек
        if (conf[11] > thr and conf[13] > thr and conf[15] > thr):
            if (left_hip[1] < left_knee[1] - 30
                    and left_knee[1] < left_ankle[1] - 30):
                return True

        if (conf[12] > thr and conf[14] > thr and conf[16] > thr):
            if (right_hip[1] < right_knee[1] - 30
                    and right_knee[1] < right_ankle[1] - 30):
                return True

        return False

    @staticmethod
    def _calculate_angle(
        point_a: np.ndarray,
        point_b: np.ndarray,
        point_c: np.ndarray,
    ) -> float:
        """
        Вычисляет угол в точке B между лучами BA и BC (в градусах).

        Args:
            point_a: первая точка (x, y)
            point_b: вершина угла (x, y)
            point_c: третья точка (x, y)

        Returns:
            Угол в градусах [0, 180]
        """
        ba = point_a - point_b
        bc = point_c - point_b

        dot_product = np.dot(ba, bc)
        magnitude_ba = np.linalg.norm(ba)
        magnitude_bc = np.linalg.norm(bc)

        if magnitude_ba == 0 or magnitude_bc == 0:
            return 180.0

        cos_angle = np.clip(dot_product / (magnitude_ba * magnitude_bc), -1.0, 1.0)
        angle = np.degrees(np.arccos(cos_angle))

        return angle

    def _smooth_pose(self, track_id: int, current_pose: str) -> str:
        """
        Сглаживает определение позы по последним N кадрам.
        Предотвращает мерцание между позами.
        """
        if track_id not in self._pose_history:
            self._pose_history[track_id] = []

        history = self._pose_history[track_id]
        history.append(current_pose)

        # Ограничиваем длину истории
        if len(history) > self._history_length:
            history.pop(0)

        # Голосование большинством
        from collections import Counter
        counter = Counter(history)
        most_common = counter.most_common(1)[0][0]

        return most_common

    def clear_track(self, track_id: int):
        """Удаляет историю для указанного трека."""
        self._pose_history.pop(track_id, None)

    def clear_all(self):
        """Очищает всю историю."""
        self._pose_history.clear()