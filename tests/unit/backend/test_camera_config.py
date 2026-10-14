import pytest
from pydantic import ValidationError

from ai_detector_core.cameras.config import CameraConfig, CameraConfigOverrides
from app.core.config import Settings


def test_overrides_preserve_inheritance() -> None:
    defaults = CameraConfig(target_fps=12, detection_confidence=0.3)
    assert CameraConfigOverrides().resolve(defaults) == defaults
    assert CameraConfigOverrides(target_fps=3).resolve(defaults) == CameraConfig(
        target_fps=3, detection_confidence=0.3
    )
    assert CameraConfigOverrides(detection_confidence=0.8).resolve(defaults).target_fps == 12


@pytest.mark.parametrize(
    "data",
    [
        {"target_fps": 0},
        {"target_fps": 31},
        {"target_fps": float("nan")},
        {"detection_confidence": 0},
        {"detection_confidence": 1.1},
        {"other": 1},
    ],
)
def test_invalid_overrides_are_rejected(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        CameraConfigOverrides.model_validate(data)


def test_api_defaults_are_configurable() -> None:
    settings = Settings(_env_file=None, target_fps=4, detection_confidence=0.5)
    assert settings.target_fps == 4
    with pytest.raises(ValidationError):
        Settings(_env_file=None, target_fps=100)
