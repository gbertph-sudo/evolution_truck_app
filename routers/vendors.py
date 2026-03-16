from fastapi import APIRouter

router = APIRouter(
    prefix="/api/vendors",
    tags=["Vendors / Suppliers"]
)

@router.get("/")
def get_vendors_root():
    return {
        "ok": True,
        "module": "vendors",
        "title": "Vendors / Suppliers",
        "status": "placeholder",
        "message": "Module scaffold ready. Business logic can be implemented later."
    }
