from photofold.config import demo_dataset_path
from photofold.dataset import validate_dataset


def test_curated_dataset_is_real_and_compatible() -> None:
    result = validate_dataset(demo_dataset_path())

    assert result["status"] == "pass"
    assert result["dataset_id"] == "hdrplus-static"
    assert result["frame_count"] == 7
    assert result["normalized_dimensions"] == {"width": 1600, "height": 1200}
    assert all(frame["format"] == "JPEG" for frame in result["frames"])
    assert all(frame["bytes"] > 0 for frame in result["frames"])

