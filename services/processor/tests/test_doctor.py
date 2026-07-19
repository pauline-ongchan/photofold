from photofold.doctor import run_doctor


def test_doctor_confirms_required_runtime() -> None:
    result = run_doctor()

    assert result["status"] == "pass"
    assert result["checks"]["webp_available"] is True
    assert result["checks"]["webp_roundtrip"] is True
    assert "compression" in result["notes"][1].lower()

