from fastapi import APIRouter

router = APIRouter(
    prefix="/labor-time-tracking",
    tags=["Labor / Time Tracking"]
)

MODULE_INFO = {
    "key": "labor_time_tracking",
    "title": "Labor / Time Tracking",
    "status": "ready-for-navigation",
    "message": "Placeholder router active. Business logic can be added later."
}

@router.get("/")
def get_labor_time_tracking_home():
    return {
        "ok": True,
        **MODULE_INFO
    }

@router.get("/meta")
def get_labor_time_tracking_meta():
    return {
        **MODULE_INFO
    }

@router.get("/health")
def get_labor_time_tracking_health():
    return {
        "ok": True,
        "module": "labor_time_tracking"
    }
