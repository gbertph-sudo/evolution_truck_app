from fastapi import APIRouter

router = APIRouter(
    prefix="/api/warranty",
    tags=["Warranty / Returns"]
)

@router.get("/")
def get_warranty_root():
    return {
        "ok": True,
        "module": "warranty",
        "title": "Warranty / Returns",
        "status": "placeholder",
        "message": "Module scaffold ready. Business logic can be implemented later."
    }
