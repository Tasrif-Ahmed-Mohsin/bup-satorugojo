"""GridWise API: real interpretation, deterministic guardrails, LP, replay.

The route returns only a payload that the independent checker has already
accepted. Errors are controlled and static: no stack trace, no request echo and
no credential ever reaches a client or a log line.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException

from app.config import Settings, load_settings
from app.directives import DirectiveValidationError, validate_directives
from app.interpreter import InterpreterError, interpret_notes
from app.jsonio import JsonPayloadError, load_json
from app.optimizer import OptimizerError, optimize_scenario, warm_up
from app.schemas import OptimizationResponse, ScenarioRequest

TOLERANCE = 0.01
logger = logging.getLogger("gridwise")
# Read once at import; the page is static and carries no credential.
_UI_PAGE = (Path(__file__).resolve().parent / "ui.html").read_text(encoding="utf-8")


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def _invalid_request() -> JSONResponse:
    return _error(400, "invalid_request", "Invalid scenario request.")


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings or load_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        # One pooled client for the whole process; connections are reused so a
        # judged request does not pay for a fresh TLS handshake every time.
        async with httpx.AsyncClient(
            headers={"Content-Type": "application/json"},
            limits=httpx.Limits(max_connections=16, max_keepalive_connections=8),
        ) as client:
            application.state.client = client
            application.state.settings = configuration
            solver_ready = await asyncio.to_thread(warm_up)
            if configuration.configured:
                # Open the connection so the first real request does not also
                # pay for DNS and the TLS handshake. This lists models; it runs
                # no inference and spends no tokens. Failure is not fatal:
                # reachability is re-established per request.
                try:
                    await client.get(
                        f"{configuration.base_url}/models",
                        headers={"Authorization": f"Bearer {configuration.api_key}"},
                        timeout=httpx.Timeout(5.0, connect=3.0),
                    )
                except httpx.HTTPError:
                    pass
            # Readiness means the process is up and the solver is warm. It does
            # not require the provider key: the published image carries no
            # secret, so an organizer starting it must still reach /health.
            # Without a key, /optimize-energy refuses with not_configured and
            # never invents a schedule. No model call is spent on a probe.
            application.state.ready = solver_ready
            if not configuration.configured:
                # Presence only; the value is never read into a log line.
                logger.warning(
                    "DEEPSEEK_API_KEY is not set; /optimize-energy will return "
                    "not_configured until it is provided."
                )
            yield

    application = FastAPI(
        title="GridWise",
        version="1.0.0",
        description="Operator notes to a validated minimum-cost 24-hour energy schedule.",
        lifespan=lifespan,
    )

    @application.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, __: RequestValidationError) -> JSONResponse:
        # Validation errors contain input values; never echo them to clients or logs.
        return _invalid_request()

    @application.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        return _error(exc.status_code, "http_error", "Request could not be handled.")

    @application.exception_handler(Exception)
    async def unexpected_error(_: Request, __: Exception) -> JSONResponse:
        return _error(500, "internal_error", "The request could not be completed.")

    @application.get("/", include_in_schema=False)
    async def demo_page() -> HTMLResponse:
        # A convenience page for humans. It calls the same public endpoint a
        # judge calls and has no privileged path of its own.
        return HTMLResponse(content=_UI_PAGE)

    @application.get("/health")
    async def health() -> JSONResponse:
        if not getattr(application.state, "ready", False):
            return JSONResponse(status_code=503, content={"status": "not_ready"})
        return JSONResponse(status_code=200, content={"status": "ok"})

    @application.post("/optimize-energy", response_model=OptimizationResponse)
    async def optimize_energy(scenario: ScenarioRequest, request: Request) -> JSONResponse:
        started = perf_counter()
        # The typed parameter documents the request schema and rejects invalid
        # input as 400. The default decoder still permits duplicate keys and
        # nonstandard constants, so check the raw document as well.
        try:
            load_json(await request.body())
        except JsonPayloadError:
            return _invalid_request()

        settings = application.state.settings
        remaining = settings.request_deadline_seconds - (perf_counter() - started)
        try:
            envelope = await interpret_notes(
                application.state.client,
                settings,
                scenario,
                budget_seconds=min(settings.model_phase_seconds, remaining),
                validate=lambda candidate: validate_directives(scenario, candidate),
            )
        except InterpreterError as error:
            return _error(500, error.code, error.message)

        try:
            directives = validate_directives(scenario, envelope)
        except DirectiveValidationError as error:
            # A rejected interpretation is a model failure, not a bad request.
            # Never relax a directive to manufacture a successful response.
            return _error(500, error.code, error.message)

        try:
            # The solver is synchronous; keep it off the event loop.
            payload = await asyncio.to_thread(
                optimize_scenario, scenario, directives, tolerance=TOLERANCE
            )
        except OptimizerError as error:
            return _error(500, error.code, error.message)

        # Returned exactly as the independent checker accepted it.
        return JSONResponse(status_code=200, content=payload)

    return application


app = create_app()
