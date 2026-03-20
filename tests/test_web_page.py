from fastapi.testclient import TestClient

from gapbf.web import create_app


def test_index_contains_success_banner(tmp_path):
    client = TestClient(create_app(str(tmp_path / "config.yaml")))

    response = client.get("/")

    assert response.status_code == 200
    assert 'id="successBanner"' in response.text
    assert 'id="copyConfigButton"' in response.text
    assert 'id="downloadCsvButton"' in response.text
    assert 'id="calculateTotalPathsButton"' in response.text
    assert 'id="resetButton"' in response.text
    assert 'id="totalPathsStateValue"' in response.text
    assert 'id="finishedAtValue"' in response.text
    assert 'id="durationValue"' in response.text
    assert 'id="noDiagonalCrossings"' in response.text
    assert 'id="noPerpendicularCrossings"' in response.text
    assert "<th>Duration</th>" not in response.text