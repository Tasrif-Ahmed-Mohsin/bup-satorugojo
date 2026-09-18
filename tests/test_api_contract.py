import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _settings(**overrides):
    values = {
        "api_key": "",
        "base_url": "https://provider.invalid",
        "model": "test-model",
        "request_deadline_seconds": 25.0,
        "model_phase_seconds": 20.0,
        "model_attempt_seconds": 9.0,
        "connect_timeout_seconds": 5.0,
        "max_output_tokens": 1024,
        "max_attempts": 2,
    }
    values.update(overrides)
    return Settings(**values)


def test_health_reports_ready_only_when_the_pipeline_is_configured():
    with TestClient(create_app(_settings(api_key="configured"))) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_health_reports_not_ready_without_provider_configuration():
    with TestClient(create_app(_settings())) as client:
        response = client.get("/health")
        assert response.status_code == 503
        assert response.json() == {"status": "not_ready"}


def test_unconfigured_provider_fails_instead_of_fabricating_a_plan(first_case):
    """A missing model must never become a schedule or a reference lookup."""
    with TestClient(create_app(_settings())) as client:
        response = client.post("/optimize-energy", json=first_case["input"])
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "not_configured"
        assert "hourly_plan" not in response.json()


def test_unreachable_provider_returns_a_controlled_error(first_case):
    with TestClient(create_app(_settings(api_key="configured"))) as client:
        response = client.post("/optimize-energy", json=first_case["input"])
        assert response.status_code == 500
        assert response.json()["error"]["code"] in {"provider_unavailable", "provider_timeout"}
        assert "configured" not in response.text
        assert "Traceback" not in response.text


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
