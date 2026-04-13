# app/main.py
import logging
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.routers import auth, projects

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

app = FastAPI(title="Launchpad", version="2.0.0")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    import traceback
    from fastapi.responses import JSONResponse
    logger = logging.getLogger("launchpad.unhandled")
    logger.error(
        "Unhandled exception on %s %s: %s\n%s",
        request.method, request.url.path,
        exc, traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}"},
    )

app.include_router(auth.router)
app.include_router(projects.router)


@app.on_event("startup")
def startup():
    from app.config import get_settings
    from app.db import get_engine
    settings = get_settings()
    os.makedirs(settings.BASE_DIR, exist_ok=True)
    get_engine(f"{settings.BASE_DIR}/projects.db")


@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok"}


# Serve Vue SPA — must be last (catch-all)
_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
