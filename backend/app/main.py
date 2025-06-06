from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from backend.app.routes import day
import os

try:
    from tools.setup_test_data import copy_test_files
except Exception:
    copy_test_files = None

app = FastAPI()

if os.getenv("LIFELOG_SETUP_TEST_DATA") == "1" and copy_test_files:
    copy_test_files()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # your Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(day.router)



# app.mount("/", StaticFiles(directory="static", html=True), name="static")
