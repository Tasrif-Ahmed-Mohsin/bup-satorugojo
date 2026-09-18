import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def test_incomplete_pipeline_does_not_report_ready():
    with TestClient(create_app()) as client:
        response = client.get("/health")
        assert response.status_code == 503
        assert response.json() == {"status": "not_ready"}


def test_valid_request_cannot_return_fake_reference(first_case):
    with TestClient(create_app()) as client:
        response = client.post("/optimize-energy", json=first_case["input"])
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "pipeline_not_ready"
        assert "hourly_plan" not in response.json()


def test_malformed_json_returns_400_without_echoing_input():
    with TestClient(create_app()) as client:
        response = client.post(
            "/optimize-energy",
            content='{"secret-marker":',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        assert "secret-marker" not in response.text


def test_bad_schema_returns_400_without_echoing_values(first_case):
    first_case["input"]["hours"][0]["demand_kwh"] = "secret-marker"
    with TestClient(create_app()) as client:
        response = client.post("/optimize-energy", json=first_case["input"])
        assert response.status_code == 400
        assert "secret-marker" not in response.text
        assert "Traceback" not in response.text


def test_openapi_describes_exact_paths_and_schema():
    spec = create_app().openapi()
    assert set(spec["paths"]) == {"/health", "/optimize-energy"}
    schema = spec["components"]["schemas"]["ScenarioRequest"]
    assert set(schema["required"]) == {"scenario_id", "operator_notes", "hours", "battery"}


@pytest.mark.parametrize("extra", ['"ignored":NaN,', '"scenario_id":"duplicate",'])
def test_rejects_nonstandard_json_even_in_ignored_metadata(first_case, extra):
    payload = "{" + extra + json.dumps(first_case["input"])[1:]
    with TestClient(create_app()) as client:
        response = client.post(
            "/optimize-energy", content=payload, headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 400
