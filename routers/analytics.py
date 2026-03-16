from fastapi import APIRouter

router = APIRouter(
    prefix="/api/analytics",
    tags=["Analytics"]
)

@router.get("/")
def get_analytics_root():
    return {
        "ok": True,
        "module": "analytics",
        "title": "Analytics",
        "status": "placeholder",
        "message": "Module scaffold ready. Business logic can be implemented later."
    }
