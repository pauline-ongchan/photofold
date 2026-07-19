import json
import zipfile

from photofold.config import REPOSITORY_ROOT
from photofold.gate1.benchmark import run_benchmark
from photofold.gate1.bundle import decode_package_frame, verify_package
from photofold.gate1.report import verify_report


def test_gate1_real_dataset_reconstructs_and_beats_matched_control(tmp_path) -> None:
    dataset = REPOSITORY_ROOT / "data/demo/hdrplus-static"
    config = REPOSITORY_ROOT / "configs/gate1.yaml"
    output = tmp_path / "gate1"

    result = run_benchmark(dataset, config, output, include_sweep=False)

    assert result["gate_pass"] is True
    assert result["accepted_frame_count"] == 7
    assert result["reconstructed_frame_count"] == 7
    assert result["package_total_bytes"] == (output / "moment.photofold").stat().st_size
    assert result["package_total_bytes"] < result["original_total_bytes"]
    assert result["relational_hypothesis_pass"] is True
    assert result["alignment_threshold_pass"] is True
    assert result["minimum_ssim"] >= result["quality_thresholds"]["min_per_frame"]
    assert result["mean_ssim"] >= result["quality_thresholds"]["min_mean"]
    assert not result["failed_checks"]
    assert [point["quality"] for point in result["independent_webp_curve"]] == list(
        range(1, 101)
    )

    verification = verify_package(output / "moment.photofold")
    assert verification["status"] == "pass"
    assert verification["package_only_decode"] is True
    assert verification["reconstructed_frame_count"] == 7
    reconstruction = decode_package_frame(output / "moment.photofold", 6)
    assert reconstruction.shape == (1200, 1600, 3)
    with zipfile.ZipFile(output / "moment.photofold") as archive:
        manifest = json.loads(archive.read("manifest.json"))
    patches = [patch for frame in manifest["frames"] for patch in frame["patches"]]
    assert patches
    assert all(patch["feather_radius"] == 2 for patch in patches)

    report = verify_report(output / "report.html", expected_frames=7)
    assert report["status"] == "pass"
    benchmark = json.loads((output / "benchmark.json").read_text(encoding="utf-8"))
    assert benchmark["package_total_bytes"] == result["package_total_bytes"]
    assert all(check["pass"] for check in benchmark["integrity_checks"])


def test_gate1_does_not_add_product_api_routes() -> None:
    from photofold.main import app

    assert set(app.openapi()["paths"]) == {"/v1/health"}
