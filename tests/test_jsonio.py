import pytest

from app.jsonio import JsonPayloadError, dump_json, load_json


@pytest.mark.parametrize(
    "payload", ['{"factor":0.2,"factor":0.8}', '{"x":NaN}', '{"x":Infinity}', b"\xff"]
)
def test_rejects_ambiguous_or_invalid_json(payload):
    with pytest.raises(JsonPayloadError):
        load_json(payload)


@pytest.mark.parametrize("number", [float("inf"), float("-inf"), float("nan")])
def test_cannot_emit_nonfinite_json(number):
    with pytest.raises(JsonPayloadError):
        dump_json({"number": number})


def test_round_trip_does_not_blanket_round_numbers():
    payload = {"grid_kwh": 1.234567891234, "battery_energy_after_kwh": 200.12345678}
    assert load_json(dump_json(payload)) == payload
