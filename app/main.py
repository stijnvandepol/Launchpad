# app/main.py
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.routers import auth, projects

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Launchpad", version="1.0.0")

app.include_router(auth.router)
app.include_router(projects.router)


@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok"}


# Serve Vue SPA — must be last (catch-all)
_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
