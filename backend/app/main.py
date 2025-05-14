from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from backend.app.routes import timeline  # ⬅️ Import the router
from backend.app.routes import summary

app = FastAPI()
app.include_router(timeline.router)
app.include_router(summary.router)


# app.mount("/", StaticFiles(directory="static", html=True), name="static")
