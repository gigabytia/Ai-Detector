"""
Продвинутый ML-классификатор поз.
Использует sklearn для обучения на фичах из ключевых точек.
Можно обучить на собранных данных для повышения точности.
"""
import numpy as np
import pickle
import os
from typing import List, Tuple, Dict, Optional
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix


class PoseFeatureExtractor:
    """Извлекает признаки из ключевых точек для ML-классификатора."""

    @staticmethod
    def extract_features(
        keypoints: np.ndarray,
        confidences: np.ndarray,
    ) -> np.ndarray:
        """
        Извлекает вектор признаков из 17 ключевых точек.

        Args:
            keypoints:    (17, 2)
            confidences:  (17,)

        Returns:
            Вектор признаков (1D numpy array)
        """
        features = []

        # ── 1. Нормализованные координаты ───────────────────
        # Нормализуем относительно bbox ключевых точек
        valid_mask = confidences > 0.3
        if valid_mask.sum() < 3:
            return np.zeros(50)

        valid_kps = keypoints[valid_mask]
        min_x, min_y = valid_kps.min(axis=0)
        max_x, max_y = valid_kps.max(axis=0)

        range_x = max(max_x - min_x, 1.0)
        range_y = max(max_y - min_y, 1.0)

        norm_kps = np.zeros_like(keypoints)
        for i in range(17):
            if confidences[i] > 0.3:
                norm_kps[i, 0] = (keypoints[i, 0] - min_x) / range_x
                norm_kps[i, 1] = (keypoints[i, 1] - min_y) / range_y

        # Нормализованные координаты как фичи
        features.extend(norm_kps.flatten())  # 34 фичи

        # ── 2. Углы суставов ────────────────────────────────
        joint_triplets = [
            (5, 7, 9),    # Левый локоть
            (6, 8, 10),   # Правый локоть
            (11, 13, 15), # Левое колено
            (12, 14, 16), # Правое колено
            (5, 11, 13),  # Левое бедро
            (6, 12, 14),  # Правое бедро
            (7, 5, 11),   # Левое плечо-торс
            (8, 6, 12),   # Правое плечо-торс
        ]

        for a, b, c in joint_triplets:
            if all(confidences[i] > 0.3 for i in [a, b, c]):
                angle = PoseFeatureExtractor._angle(
                    keypoints[a], keypoints[b], keypoints[c]
                )
                features.append(angle / 180.0)  # Нормализуем [0, 1]
            else:
                features.append(0.0)
        # 8 фичей

        # ── 3. Относительные расстояния ─────────────────────
        # Запястье-плечо (для поднятой руки)
        for w, s in [(9, 5), (10, 6)]:
            if confidences[w] > 0.3 and confidences[s] > 0.3:
                diff_y = (keypoints[s, 1] - keypoints[w, 1]) / range_y
                features.append(diff_y)
            else:
                features.append(0.0)
        # 2 фичи

        # Бедро-колено (для сидения)
        for h, k in [(11, 13), (12, 14)]:
            if confidences[h] > 0.3 and confidences[k] > 0.3:
                diff_y = (keypoints[k, 1] - keypoints[h, 1]) / range_y
                features.append(diff_y)
            else:
                features.append(0.0)
        # 2 фичи

        # ── 4. Соотношение ширины к высоте ──────────────────
        aspect_ratio = range_x / range_y
        features.append(aspect_ratio)
        # 1 фича

        # ── 5. Центры масс частей тела ──────────────────────
        # Верхняя часть (плечи, голова)
        upper_indices = [0, 1, 2, 3, 4, 5, 6]
        upper_valid = [i for i in upper_indices if confidences[i] > 0.3]
        if upper_valid:
            upper_center_y = np.mean([norm_kps[i, 1] for i in upper_valid])
        else:
            upper_center_y = 0.0
        features.append(upper_center_y)

        # Нижняя часть (бёдра, колени, лодыжки)
        lower_indices = [11, 12, 13, 14, 15, 16]
        lower_valid = [i for i in lower_indices if confidences[i] > 0.3]
        if lower_valid:
            lower_center_y = np.mean([norm_kps[i, 1] for i in lower_valid])
        else:
            lower_center_y = 1.0
        features.append(lower_center_y)

        # Разница центров масс
        features.append(lower_center_y - upper_center_y)
        # 3 фичи

        # Итого: 34 + 8 + 2 + 2 + 1 + 3 = 50 фичей
        return np.array(features, dtype=np.float32)

    @staticmethod
    def _angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
        """Угол в точке b."""
        ba = a - b
        bc = c - b
        dot = np.dot(ba, bc)
        mag_ba = np.linalg.norm(ba)
        mag_bc = np.linalg.norm(bc)
        if mag_ba == 0 or mag_bc == 0:
            return 180.0
        cos_angle = np.clip(dot / (mag_ba * mag_bc), -1.0, 1.0)
        return float(np.degrees(np.arccos(cos_angle)))


class PoseMLClassifier:
    """
    ML-классификатор поз, обучаемый на данных.
    Использует RandomForest или GradientBoosting.
    """

    def __init__(self, model_type: str = "random_forest"):
        self.feature_extractor = PoseFeatureExtractor()
        self.scaler = StandardScaler()
        self.model_type = model_type

        if model_type == "random_forest":
            self.model = RandomForestClassifier(
                n_estimators=200,
                max_depth=15,
                min_samples_split=5,
                random_state=42,
                n_jobs=-1,
            )
        elif model_type == "gradient_boosting":
            self.model = GradientBoostingClassifier(
                n_estimators=200,
                max_depth=5,
                learning_rate=0.1,
                random_state=42,
            )
        else:
            raise ValueError(f"Неизвестный тип модели: {model_type}")

        self._is_trained = False

    def train(
        self,
        keypoints_list: List[np.ndarray],
        confidences_list: List[np.ndarray],
        labels: List[str],
        test_size: float = 0.2,
    ) -> Dict:
        """
        Обучает классификатор.

        Args:
            keypoints_list:   список (17, 2) массивов
            confidences_list: список (17,) массивов
            labels:           список меток ("standing", "sitting", "hand_raised")
            test_size:        доля тестовой выборки

        Returns:
            Словарь с метриками
        """
        print(f"[TRAIN] Извлечение признаков из {len(labels)} примеров...")

        # Извлечение признаков
        X = np.array([
            self.feature_extractor.extract_features(kp, conf)
            for kp, conf in zip(keypoints_list, confidences_list)
        ])
        y = np.array(labels)

        print(f"[TRAIN] Размер матрицы признаков: {X.shape}")
        print(f"[TRAIN] Распределение классов: ", end="")
        unique, counts = np.unique(y, return_counts=True)
        for u, c in zip(unique, counts):
            print(f"{u}={c} ", end="")
        print()

        # Разделение на обучение и тест
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y,
        )

        # Нормализация
        X_train = self.scaler.fit_transform(X_train)
        X_test = self.scaler.transform(X_test)

        # Обучение
        print(f"[TRAIN] Обучение модели ({self.model_type})...")
        self.model.fit(X_train, y_train)
        self._is_trained = True

        # Оценка
        y_pred = self.model.predict(X_test)
        accuracy = np.mean(y_pred == y_test)

        print(f"\n[TRAIN] Точность на тесте: {accuracy:.4f}")
        print("\n[TRAIN] Отчёт классификации:")
        print(classification_report(y_test, y_pred))

        # Кросс-валидация
        X_scaled = self.scaler.transform(X)
        cv_scores = cross_val_score(self.model, X_scaled, y, cv=5)
        print(f"[TRAIN] Кросс-валидация (5 фолдов): {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")

        return {
            "accuracy": accuracy,
            "cv_mean": cv_scores.mean(),
            "cv_std": cv_scores.std(),
            "report": classification_report(y_test, y_pred, output_dict=True),
        }

    def predict(
        self,
        keypoints: np.ndarray,
        confidences: np.ndarray,
    ) -> Tuple[str, Dict[str, float]]:
        """
        Предсказывает позу.

        Returns:
            (pose_label, probability_dict)
        """
        if not self._is_trained:
            raise RuntimeError("Модель не обучена! Вызовите train() или load().")

        features = self.feature_extractor.extract_features(keypoints, confidences)
        features_scaled = self.scaler.transform(features.reshape(1, -1))

        label = self.model.predict(features_scaled)[0]
        probas = self.model.predict_proba(features_scaled)[0]
        classes = self.model.classes_

        scores = {cls: float(prob) for cls, prob in zip(classes, probas)}

        return label, scores

    def save(self, path: str = "pose_ml_model.pkl"):
        """Сохраняет модель."""
        data = {
            "model": self.model,
            "scaler": self.scaler,
            "model_type": self.model_type,
        }
        with open(path, 'wb') as f:
            pickle.dump(data, f)
        print(f"[INFO] ML-модель сохранена: {path}")

    def load(self, path: str = "pose_ml_model.pkl"):
        """Загружает модель."""
        with open(path, 'rb') as f:
            data = pickle.load(f)
        self.model = data["model"]
        self.scaler = data["scaler"]
        self.model_type = data["model_type"]
        self._is_trained = True
        print(f"[INFO] ML-модель загружена: {path}")


def generate_synthetic_training_data(
    n_samples_per_class: int = 500,
) -> Tuple[List[np.ndarray], List[np.ndarray], List[str]]:
    """
    Генерирует синтетические данные для обучения.
    Используется для демонстрации — для реального проекта
    нужны реальные данные!

    Returns:
        (keypoints_list, confidences_list, labels)
    """
    np.random.seed(42)

    keypoints_list = []
    confidences_list = []
    labels = []

    def add_noise(kps, scale=10.0):
        return kps + np.random.randn(*kps.shape) * scale

    for _ in range(n_samples_per_class):
        # ── Стоящий человек ─────────────────────────────
        standing_kps = np.array([
            [300, 100],  # nose
            [290, 90],   # left_eye
            [310, 90],   # right_eye
            [280, 95],   # left_ear
            [320, 95],   # right_ear
            [270, 170],  # left_shoulder
            [330, 170],  # right_shoulder
            [250, 250],  # left_elbow
            [350, 250],  # right_elbow
            [240, 330],  # left_wrist
            [360, 330],  # right_wrist
            [280, 350],  # left_hip
            [320, 350],  # right_hip
            [275, 480],  # left_knee
            [325, 480],  # right_knee
            [270, 600],  # left_ankle
            [330, 600],  # right_ankle
        ], dtype=np.float32)

        kps = add_noise(standing_kps, 15.0)
        conf = np.random.uniform(0.5, 1.0, 17).astype(np.float32)
        keypoints_list.append(kps)
        confidences_list.append(conf)
        labels.append("standing")

        # ── Сидящий человек ─────────────────────────────
        sitting_kps = np.array([
            [300, 100],  # nose
            [290, 90],   # left_eye
            [310, 90],   # right_eye
            [280, 95],   # left_ear
            [320, 95],   # right_ear
            [270, 170],  # left_shoulder
            [330, 170],  # right_shoulder
            [250, 250],  # left_elbow
            [350, 250],  # right_elbow
            [240, 330],  # left_wrist
            [360, 330],  # right_wrist
            [280, 340],  # left_hip
            [320, 340],  # right_hip
            [275, 350],  # left_knee (почти на уровне бёдер)
            [325, 350],  # right_knee
            [270, 450],  # left_ankle
            [330, 450],  # right_ankle
        ], dtype=np.float32)

        kps = add_noise(sitting_kps, 15.0)
        conf = np.random.uniform(0.5, 1.0, 17).astype(np.float32)
        keypoints_list.append(kps)
        confidences_list.append(conf)
        labels.append("sitting")

        # ── Поднятая рука ───────────────────────────────
        hand_raised_kps = np.array([
            [300, 100],  # nose
            [290, 90],   # left_eye
            [310, 90],   # right_eye
            [280, 95],   # left_ear
            [320, 95],   # right_ear
            [270, 170],  # left_shoulder
            [330, 170],  # right_shoulder
            [260, 110],  # left_elbow (поднят вверх)
            [350, 250],  # right_elbow
            [270, 50],   # left_wrist (выше головы)
            [360, 330],  # right_wrist
            [280, 350],  # left_hip
            [320, 350],  # right_hip
            [275, 480],  # left_knee
            [325, 480],  # right_knee
            [270, 600],  # left_ankle
            [330, 600],  # right_ankle
        ], dtype=np.float32)

        kps = add_noise(hand_raised_kps, 15.0)
        conf = np.random.uniform(0.5, 1.0, 17).astype(np.float32)
        keypoints_list.append(kps)
        confidences_list.append(conf)
        labels.append("hand_raised")

    print(f"[DATA] Сгенерировано {len(labels)} примеров")
    return keypoints_list, confidences_list, labels