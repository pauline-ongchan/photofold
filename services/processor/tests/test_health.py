from fastapi.testclient import TestClient

from photofold.main import app


def test_health_exposes_only_real_phase_zero_readiness() -> None:
    response = TestClient(app).get("/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["webp_available"] is True
    assert payload["webp_roundtrip"] is True
    assert payload["dataset"]["id"] == "hdrplus-static"
    assert payload["dataset"]["frame_count"] == 7
    assert any("not implemented" in item for item in payload["limitations"])


def test_phase_zero_has_no_future_product_routes() -> None:
    paths = set(app.openapi()["paths"])

    assert paths == {"/v1/health"}

