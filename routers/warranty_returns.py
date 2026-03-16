from fastapi import APIRouter

router = APIRouter(
    prefix="/roles-permissions",
    tags=["Roles & Permissions"]
)

MODULE_INFO = {
    "key": "roles_permissions",
    "title": "Roles & Permissions",
    "status": "ready-for-navigation",
    "message": "Placeholder router active. Business logic can be added later."
}

@router.get("/")
def get_roles_permissions_home():
    return {
        "ok": True,
        **MODULE_INFO
    }

@router.get("/meta")
def get_roles_permissions_meta():
    return {
        **MODULE_INFO
    }

@router.get("/health")
def get_roles_permissions_health():
    return {
        "ok": True,
        "module": "roles_permissions"
    }
