from fastapi import APIRouter

router = APIRouter(
    prefix="/api/pos",
    tags=["Parts Store (POS)"]
)

@router.get("/")
def get_pos_root():
    return {
        "ok": True,
        "module": "pos",
        "title": "Parts Store (POS)",
        "status": "placeholder",
        "message": "Module scaffold ready. Business logic can be implemented later."
    }
