import pytest

from ai_detector_core.cameras.source import (
    InvalidSourceError,
    SourceType,
    mask_source_url,
    mock_scenario,
    upload_ref,
    validate_source_url,
)

REF = "0123456789abcdef0123456789abcdef.mp4"


@pytest.mark.parametrize(
    ("source_type", "url"),
    [
        (SourceType.RTSP, "rtsp://user:pass@10.0.0.5:554/stream1"),
        (SourceType.RTSP, "rtsps://camera.local/live"),
        (SourceType.FILE, f"upload://{REF}"),
        (SourceType.MOCK, "mock://walk_through"),
    ],
)
def test_valid_sources_are_accepted(source_type: SourceType, url: str) -> None:
    assert validate_source_url(source_type, url) == url


@pytest.mark.parametrize(
    ("source_type", "url"),
    [
        (SourceType.RTSP, "http://camera.local/stream"),
        (SourceType.RTSP, "rtsp:///no-host"),
        (SourceType.RTSP, "rtsp://host:notaport/x"),
        (SourceType.RTSP, "rtsp://host/with space"),
        (SourceType.RTSP, ""),
        (SourceType.FILE, "/etc/passwd"),
        (SourceType.FILE, "upload://../../etc/passwd"),
        (SourceType.FILE, "upload://0123456789abcdef0123456789abcdef.exe"),
        (SourceType.FILE, "file:///data/video.mp4"),
        (SourceType.MOCK, "mock://../secret"),
        (SourceType.MOCK, "mock://"),
        (SourceType.MOCK, f"upload://{REF}"),
    ],
)
def test_invalid_sources_are_rejected(source_type: SourceType, url: str) -> None:
    with pytest.raises(InvalidSourceError):
        validate_source_url(source_type, url)


def test_helpers_extract_names() -> None:
    assert upload_ref(f"upload://{REF}") == REF
    assert mock_scenario("mock://two_people") == "two_people"


@pytest.mark.parametrize(
    ("url", "masked"),
    [
        ("rtsp://admin:s3cret@10.0.0.5:554/s1", "rtsp://***:***@10.0.0.5:554/s1"),
        ("rtsp://admin@cam.local/s1", "rtsp://***:***@cam.local/s1"),
        ("rtsp://u:p@[fe80::1]:8554/s", "rtsp://***:***@[fe80::1]:8554/s"),
        ("rtsp://cam.local/s1", "rtsp://cam.local/s1"),
        ("mock://walk_through", "mock://walk_through"),
    ],
)
def test_mask_source_url_hides_credentials(url: str, masked: str) -> None:
    assert mask_source_url(url) == masked
    assert "s3cret" not in mask_source_url(url)
