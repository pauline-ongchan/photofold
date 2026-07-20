def test_phase1b_does_not_add_product_api_routes() -> None:
    from photofold.main import app

    assert set(app.openapi()["paths"]) == {"/v1/health"}
