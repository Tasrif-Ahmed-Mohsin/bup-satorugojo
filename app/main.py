"""Contract scaffold. Step 3 deliberately does not claim an operational pipeline."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.jsonio import JsonPayloadError, load_json
from app.schemas import OptimizationResponse, ScenarioRequest


def create_app() -> FastAPI:
    application = FastAPI(
        title="GridWise",
        version="0.1.0",
        description="Step 3 contract and validation foundation; optimization is not wired yet.",
    )

    @application.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, __: RequestValidationError) -> JSONResponse:
        # Validation errors contain input values; never echo them to clients or logs.
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "invalid_request", "message": "Invalid scenario request."}},
        )

    @application.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "http_error", "message": "Request could not be handled."}},
            headers=exc.headers,
        )

    @application.get("/health")
    async def health() -> JSONResponse:
        # Only the complete interpreter/solver pipeline may report status='ok'.
        return JSONResponse(status_code=503, content={"status": "not_ready"})

    @application.post("/optimize-energy", response_model=OptimizationResponse)
    async def optimize_energy(scenario: ScenarioRequest, request: Request) -> JSONResponse:
        # The default decoder permits duplicate keys and nonstandard constants.
        # Validate the raw document as well, including any ignored input metadata.
        try:
            load_json(await request.body())
        except JsonPayloadError:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {"code": "invalid_request", "message": "Invalid scenario request."}
                },
            )
        # Never substitute a public reference or fabricated no_op for real model work.
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "pipeline_not_ready",
                    "message": "The optimization service is not ready.",
                }
            },
        )

    return application


app = create_app()
