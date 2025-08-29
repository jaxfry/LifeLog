from fastapi import FastAPI
from contextlib import asynccontextmanager

from .api import ingestion, extensions, event_types, processing
from .actors import load_all_actors

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("INFO:     Application starting up...")
    load_all_actors()
    print("INFO:     Application startup complete.")
    yield
    print("INFO:     Shutting down application.")

app = FastAPI(
    title="LifeLog API",
    description="The central server for the LifeLog system.",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(ingestion.router)
app.include_router(extensions.router)
app.include_router(event_types.router)
app.include_router(processing.router)

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Welcome to the LifeLog API!"}
