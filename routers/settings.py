from fastapi import APIRouter

router = APIRouter(
    prefix="/api/settings",
    tags=["Settings"]
)

@router.get("/")
def get_settings_root():
    return {
        "ok": True,
        "module": "settings",
        "title": "Settings",
        "status": "placeholder",
        "message": "Module scaffold ready. Business logic can be implemented later."
    }
