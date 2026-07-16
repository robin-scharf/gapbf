from fastapi.testclient import TestClient

from gapbf.web import create_app


def test_index_serves_spa_shell(tmp_path):
    client = TestClient(create_app(str(tmp_path / "config.yaml")))

    response = client.get("/")

    assert response.status_code == 200
    # The UI is now a Preact app mounted into #app (no server-side markup).
    assert '<div id="app"></div>' in response.text
    assert "/assets/ui/main.js" in response.text
    assert '"preact"' in response.text  # import map


def test_static_assets_served(tmp_path):
    client = TestClient(create_app(str(tmp_path / "config.yaml")))

    for path in (
        "/assets/ui/main.js",
        "/assets/ui/store.js",
        "/assets/vendor/preact.module.js",
        "/assets/styles.css",
    ):
        assert client.get(path).status_code == 200, path
