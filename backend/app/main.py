from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from backend.app.routes import timeline  # ⬅️ Import the router
from backend.app.routes import summary
from backend.app.routes import day

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # your Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(timeline.router)
app.include_router(summary.router)
app.include_router(day.router)



# app.mount("/", StaticFiles(directory="static", html=True), name="static")
