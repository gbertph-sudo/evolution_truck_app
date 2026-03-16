from fastapi import APIRouter

router = APIRouter(
    prefix="/api/purchase-orders",
    tags=["Purchase Orders"]
)

@router.get("/")
def get_purchase_orders_root():
    return {
        "ok": True,
        "module": "purchase_orders",
        "title": "Purchase Orders",
        "status": "placeholder",
        "message": "Module scaffold ready. Business logic can be implemented later."
    }
