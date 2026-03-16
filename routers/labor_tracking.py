from fastapi import APIRouter

router = APIRouter(
    prefix="/api/labor-tracking",
    tags=["Labor / Time Tracking"]
)

@router.get("/")
def get_labor_tracking_root():
    return {
        "ok": True,
        "module": "labor_tracking",
        "title": "Labor / Time Tracking",
        "status": "placeholder",
        "message": "Module scaffold ready. Business logic can be implemented later."
    }
