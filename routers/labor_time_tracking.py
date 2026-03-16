from fastapi import APIRouter

router = APIRouter(
    prefix="/warranty-returns",
    tags=["Warranty / Returns"]
)

MODULE_INFO = {
    "key": "warranty_returns",
    "title": "Warranty / Returns",
    "status": "ready-for-navigation",
    "message": "Placeholder router active. Business logic can be added later."
}

@router.get("/")
def get_warranty_returns_home():
    return {
        "ok": True,
        **MODULE_INFO
    }

@router.get("/meta")
def get_warranty_returns_meta():
    return {
        **MODULE_INFO
    }

@router.get("/health")
def get_warranty_returns_health():
    return {
        "ok": True,
        "module": "warranty_returns"
    }
