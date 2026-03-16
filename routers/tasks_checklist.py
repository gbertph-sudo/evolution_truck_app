from fastapi import APIRouter

router = APIRouter(
    prefix="/analytics",
    tags=["Analytics"]
)

MODULE_INFO = {
    "key": "analytics",
    "title": "Analytics",
    "status": "ready-for-navigation",
    "message": "Placeholder router active. Business logic can be added later."
}

@router.get("/")
def get_analytics_home():
    return {
        "ok": True,
        **MODULE_INFO
    }

@router.get("/meta")
def get_analytics_meta():
    return {
        **MODULE_INFO
    }

@router.get("/health")
def get_analytics_health():
    return {
        "ok": True,
        "module": "analytics"
    }
