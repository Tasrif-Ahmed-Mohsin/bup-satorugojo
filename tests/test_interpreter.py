"""Provider-boundary checks using a stub transport; no real model is called.

These tests establish that untrusted provider output is handled safely. They
say nothing about the real model's accuracy, which is measured separately by
``scripts/measure_interpretation.py`` against the live provider.
"""

import json

import httpx
import pytest

from app.config import Settings, load_settings
from app.directives import DirectiveValidationError, validate_directives
from app.interpreter import InterpreterError, build_prompt, interpret_notes
from app.schemas import ScenarioRequest

SETTINGS = Settings(
    api_key="test-key-not-real",
    base_url="https://provider.invalid",
    model="test-model",
    request_deadline_seconds=25.0,
    model_phase_seconds=20.0,
    model_attempt_seconds=9.0,
    connect_timeout_seconds=5.0,
    max_output_tokens=1024,
    max_attempts=2,
)


def _scenario(notes=("Solar drops to 20% from 1 PM to 3 PM.",), capacity=200):
    return ScenarioRequest.model_validate(
        {
            "scenario_id": "stub-case",
            "operator_notes": list(notes),
            "hours": [
                {"hour": hour, "demand_kwh": 100, "solar_kwh": 30, "tariff_bdt_per_kwh": 7}
                for hour in range(24)
            ],
            "battery": {
                "capacity_kwh": capacity,
                "initial_energy_kwh": 100,
                "minimum_energy_kwh": 20,
                "max_charge_kwh_per_hour": 40,
                "max_discharge_kwh_per_hour": 40,
            },
        }
    )


def _completion(content):
    return {"choices": [{"message": {"content": content}}]}


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://stub")


def _responder(*responses):
    """Return each queued response in turn, repeating the last one."""
    queue = list(responses)
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return queue.pop(0) if len(queue) > 1 else queue[0]

    handler.calls = calls
    return handler


VALID_CONTENT = json.dumps(
    {
        "directive_interpretation": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "solar_reduction",
                "structured_adjustment": {"hours": [13, 14], "factor": 0.2},
                "explanation": "Usable solar falls to a fifth for those hours.",
            }
        ]
    }
)


@pytest.mark.anyio
async def test_valid_model_output_is_returned_and_validates():
    handler = _responder(httpx.Response(200, json=_completion(VALID_CONTENT)))
    async with _client(handler) as client:
        scenario = _scenario()
        envelope = await interpret_notes(client, SETTINGS, scenario)
    directives = validate_directives(scenario, envelope)
    assert directives[0].directive_type == "solar_reduction"
    assert directives[0].structured_adjustment.hours == [13, 14]


@pytest.mark.anyio
async def test_request_disables_thinking_and_asks_for_a_json_object():
    handler = _responder(httpx.Response(200, json=_completion(VALID_CONTENT)))
    async with _client(handler) as client:
        await interpret_notes(client, SETTINGS, _scenario())
    body = handler.calls[0]
    assert body["model"] == "test-model"
    assert body["response_format"] == {"type": "json_object"}
    assert body["thinking"] == {"type": "disabled"}
    assert body["stream"] is False
    assert body["temperature"] == 0


@pytest.mark.anyio
async def test_unusable_output_is_retried_once_then_reported():
    handler = _responder(
        httpx.Response(200, json=_completion("not json at all")),
        httpx.Response(200, json=_completion(VALID_CONTENT)),
    )
    async with _client(handler) as client:
        envelope = await interpret_notes(client, SETTINGS, _scenario())
    assert len(handler.calls) == 2
    assert envelope["directive_interpretation"][0]["directive_type"] == "solar_reduction"


@pytest.mark.anyio
async def test_persistently_unusable_output_raises_a_static_error():
    handler = _responder(httpx.Response(200, json=_completion("{")))
    async with _client(handler) as client:
        with pytest.raises(InterpreterError) as error:
            await interpret_notes(client, SETTINGS, _scenario())
    assert error.value.code == "invalid_model_output"
    assert len(handler.calls) == SETTINGS.max_attempts


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 402, 403])
async def test_credential_and_credit_failures_are_not_retried(status):
    handler = _responder(httpx.Response(status, json={"error": "denied"}))
    async with _client(handler) as client:
        with pytest.raises(InterpreterError) as error:
            await interpret_notes(client, SETTINGS, _scenario())
    assert error.value.code == "provider_unavailable"
    assert len(handler.calls) == 1


@pytest.mark.anyio
async def test_server_errors_are_retried_within_the_budget():
    handler = _responder(
        httpx.Response(503, json={"error": "busy"}),
        httpx.Response(200, json=_completion(VALID_CONTENT)),
    )
    async with _client(handler) as client:
        envelope = await interpret_notes(client, SETTINGS, _scenario())
    assert len(handler.calls) == 2
    assert "directive_interpretation" in envelope


@pytest.mark.anyio
async def test_timeouts_produce_a_static_timeout_error():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    async with _client(handler) as client:
        with pytest.raises(InterpreterError) as error:
            await interpret_notes(client, SETTINGS, _scenario())
    assert error.value.code == "provider_timeout"


@pytest.mark.anyio
async def test_a_missing_note_is_rejected_rather_than_filled_with_no_op():
    """A short interpretation must fail, never be padded into a valid answer."""
    handler = _responder(httpx.Response(200, json=_completion(VALID_CONTENT)))
    scenario = _scenario(("Solar drops to 20% from 1 PM to 3 PM.", "Do not charge at 2 PM."))
    async with _client(handler) as client:
        envelope = await interpret_notes(client, SETTINGS, scenario)
    with pytest.raises(DirectiveValidationError) as error:
        validate_directives(scenario, envelope)
    assert error.value.code == "note_count_mismatch"


@pytest.mark.anyio
async def test_unsupported_directive_types_are_rejected():
    content = json.dumps(
        {
            "directive_interpretation": [
                {
                    "note_index": 0,
                    "applies": True,
                    "directive_type": "shed_demand",
                    "structured_adjustment": {"hours": [13], "amount_kwh": 50},
                    "explanation": "Invented type.",
                }
            ]
        }
    )
    handler = _responder(httpx.Response(200, json=_completion(content)))
    scenario = _scenario()
    async with _client(handler) as client:
        envelope = await interpret_notes(client, SETTINGS, scenario)
    with pytest.raises(DirectiveValidationError) as error:
        validate_directives(scenario, envelope)
    assert error.value.code == "invalid_directives"


@pytest.mark.anyio
async def test_an_unconfigured_provider_is_never_called():
    handler = _responder(httpx.Response(200, json=_completion(VALID_CONTENT)))
    async with _client(handler) as client:
        with pytest.raises(InterpreterError) as error:
            await interpret_notes(
                client, Settings(**{**SETTINGS.__dict__, "api_key": ""}), _scenario()
            )
    assert error.value.code == "not_configured"
    assert handler.calls == []


@pytest.mark.anyio
async def test_provider_errors_never_expose_the_credential():
    handler = _responder(httpx.Response(500, text="upstream failure"))
    async with _client(handler) as client:
        with pytest.raises(InterpreterError) as error:
            await interpret_notes(client, SETTINGS, _scenario())
    assert SETTINGS.api_key not in str(error.value)


def test_prompt_states_the_rules_and_delimits_the_notes():
    marker = "ZZ-NOTE-MARKER"
    prompt = build_prompt(_scenario((f"Solar halves at noon. {marker}",), capacity=500))
    assert "<notes>" in prompt and "[0] " in prompt
    assert marker in prompt  # the note is data inside the delimited block
    assert "500.0 kWh" in prompt  # capacity for percentage reserves
    assert "excludes its end hour" in prompt
    assert "usable fraction of solar that REMAINS" in prompt


def test_settings_never_expose_the_key_through_repr_of_the_app_config():
    settings = load_settings()
    # Presence only; the value must not be asserted on or printed anywhere.
    assert isinstance(settings.configured, bool)
    assert settings.model
    assert settings.request_deadline_seconds <= 30


TWO_NOTES = ("Solar drops to 20% from 1 PM to 3 PM.", "Do not charge at 2 PM.")
VALID_TWO = json.dumps(
    {
        "directive_interpretation": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "solar_reduction",
                "structured_adjustment": {"hours": [13, 14], "factor": 0.2},
                "explanation": "Usable solar falls to a fifth for those hours.",
            },
            {
                "note_index": 1,
                "applies": True,
                "directive_type": "no_charge_window",
                "structured_adjustment": {"hours": [14]},
                "explanation": "Charging is not allowed at 2 PM.",
            },
        ]
    }
)


def _validator(scenario):
    return lambda envelope: validate_directives(scenario, envelope)


@pytest.mark.anyio
async def test_a_reply_rejected_by_the_guardrails_is_repaired_once():
    """One entry for two notes fails validation; the corrected retry succeeds."""
    handler = _responder(
        httpx.Response(200, json=_completion(VALID_CONTENT)),
        httpx.Response(200, json=_completion(VALID_TWO)),
    )
    scenario = _scenario(TWO_NOTES)
    async with _client(handler) as client:
        envelope = await interpret_notes(client, SETTINGS, scenario, validate=_validator(scenario))
    assert len(handler.calls) == 2
    assert len(validate_directives(scenario, envelope)) == 2
    first, second = (call["messages"][1]["content"] for call in handler.calls)
    assert "rejected by validation" not in first
    assert "rejected by validation" in second and "exactly 2 entries" in second


@pytest.mark.anyio
async def test_a_valid_reply_is_never_retried():
    handler = _responder(httpx.Response(200, json=_completion(VALID_CONTENT)))
    scenario = _scenario()
    async with _client(handler) as client:
        await interpret_notes(client, SETTINGS, scenario, validate=_validator(scenario))
    assert len(handler.calls) == 1


@pytest.mark.anyio
async def test_a_reply_that_stays_invalid_still_fails_downstream():
    """The retry never pads or drops a note to force validation to pass."""
    handler = _responder(httpx.Response(200, json=_completion(VALID_CONTENT)))
    scenario = _scenario(TWO_NOTES)
    async with _client(handler) as client:
        envelope = await interpret_notes(client, SETTINGS, scenario, validate=_validator(scenario))
    assert len(handler.calls) == SETTINGS.max_attempts
    with pytest.raises(DirectiveValidationError) as error:
        validate_directives(scenario, envelope)
    assert error.value.code == "note_count_mismatch"


@pytest.mark.anyio
async def test_the_correction_never_quotes_note_text():
    marker = "ZZ-NOTE-MARKER"
    handler = _responder(
        httpx.Response(200, json=_completion(VALID_CONTENT)),
        httpx.Response(200, json=_completion(VALID_TWO)),
    )
    scenario = _scenario((f"Solar drops to 20% from 1 PM to 3 PM. {marker}", TWO_NOTES[1]))
    async with _client(handler) as client:
        await interpret_notes(client, SETTINGS, scenario, validate=_validator(scenario))
    after_notes = handler.calls[1]["messages"][1]["content"].split("</notes>", 1)[1]
    assert marker not in after_notes
