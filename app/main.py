# app/main.py
from fastapi import FastAPI
from app.routers import auth, projects

app = FastAPI(title="Launchpad", version="1.0.0")

app.include_router(auth.router)
app.include_router(projects.router)


@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok"}
