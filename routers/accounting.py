from fastapi import APIRouter

router = APIRouter(
    prefix="/api/accounting",
    tags=["Accounting / Ledger"]
)

@router.get("/")
def get_accounting_root():
    return {
        "ok": True,
        "module": "accounting",
        "title": "Accounting / Ledger",
        "status": "placeholder",
        "message": "Module scaffold ready. Business logic can be implemented later."
    }
