"""FastAPI foundation boundary; Gate 1 remains CLI-only."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from photofold import __version__
from photofold.config import allowed_origins
from photofold.contracts import HealthResponse
from photofold.health import health_response

app = FastAPI(
    title="PhotoFold Processor",
    summary="Deterministic PhotoFold processor boundary",
    description=(
        "The API exposes capability and curated-dataset health only. "
        "Gate 1 compression and reconstruction remain CLI-only; uploads, jobs, and model calls "
        "are not implemented."
    ),
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Content-Type"],
)


@app.get(
    "/v1/health",
    response_model=HealthResponse,
    tags=["system"],
    summary="Report deterministic processor and demo-dataset readiness",
)
def get_health() -> HealthResponse:
    return health_response()
