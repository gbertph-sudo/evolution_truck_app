from fastapi import APIRouter

router = APIRouter(
    prefix="/payments",
    tags=["Payments"]
)

MODULE_INFO = {
    "key": "payments",
    "title": "Payments",
    "status": "ready-for-navigation",
    "message": "Placeholder router active. Business logic can be added later."
}

@router.get("/")
def get_payments_home():
    return {
        "ok": True,
        **MODULE_INFO
    }

@router.get("/meta")
def get_payments_meta():
    return {
        **MODULE_INFO
    }

@router.get("/health")
def get_payments_health():
    return {
        "ok": True,
        "module": "payments"
    }
