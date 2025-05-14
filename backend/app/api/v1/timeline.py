from fastapi import APIRouter
from datetime import date

router = APIRouter()

@router.get("/timeline/{day}")
def get_timeline(day: date):
    return {"day": str(day), "status": "not yet implemented"}
