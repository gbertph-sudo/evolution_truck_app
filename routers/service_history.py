from fastapi import APIRouter

router = APIRouter(
    prefix="/api/service-history",
    tags=["Service History"]
)

@router.get("/")
def get_service_history_root():
    return {
        "ok": True,
        "module": "service_history",
        "title": "Service History",
        "status": "placeholder",
        "message": "Module scaffold ready. Business logic can be implemented later."
    }
