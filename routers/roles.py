from fastapi import APIRouter

router = APIRouter(
    prefix="/api/roles",
    tags=["Roles & Permissions"]
)

@router.get("/")
def get_roles_root():
    return {
        "ok": True,
        "module": "roles",
        "title": "Roles & Permissions",
        "status": "placeholder",
        "message": "Module scaffold ready. Business logic can be implemented later."
    }
