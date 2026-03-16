from fastapi import APIRouter

router = APIRouter(
    prefix="/api/reports",
    tags=["Reports"]
)

@router.get("/")
def get_reports_root():
    return {
        "ok": True,
        "module": "reports",
        "title": "Reports",
        "status": "placeholder",
        "message": "Module scaffold ready. Business logic can be implemented later."
    }
