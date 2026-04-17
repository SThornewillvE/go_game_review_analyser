from fastapi import FastAPI

from src.pipeline import db
from src.routers import analyses, auth, pipeline

app = FastAPI(title="Go Game Review Analyser")

db.initialise_db()

app.include_router(auth.router)
app.include_router(pipeline.router)
app.include_router(analyses.router)


@app.get("/health")
def health():
    return {"status": "ok"}
