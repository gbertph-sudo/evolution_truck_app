from fastapi import APIRouter

router = APIRouter(
    prefix="/api/payments",
    tags=["Payments"]
)

@router.get("/")
def get_payments_root():
    return {
        "ok": True,
        "module": "payments",
        "title": "Payments",
        "status": "placeholder",
        "message": "Module scaffold ready. Business logic can be implemented later."
    }
