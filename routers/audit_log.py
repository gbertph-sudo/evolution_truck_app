from fastapi import APIRouter

router = APIRouter(
    prefix="/api/audit-log",
    tags=["Audit Log"]
)

@router.get("/")
def get_audit_log_root():
    return {
        "ok": True,
        "module": "audit_log",
        "title": "Audit Log",
        "status": "placeholder",
        "message": "Module scaffold ready. Business logic can be implemented later."
    }
