import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.rest.app import api_routers
from src.config.settings import get_settings
from src.core.logging import configure_logging

settings = get_settings()
configure_logging(settings, service_name="studyguru-concept-visual-backend")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="StudyGuru Concept Visual Backend",
    description="Standalone AI-backed concept visual generation backend.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_routers)


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    """Return a lightweight service metadata payload."""

    return {"service": "StudyGuru Concept Visual Backend", "status": "running"}
