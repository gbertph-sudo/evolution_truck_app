from fastapi import APIRouter

router = APIRouter(
    prefix="/tasks-checklist",
    tags=["Tasks / Checklist"]
)

MODULE_INFO = {
    "key": "tasks_checklist",
    "title": "Tasks / Checklist",
    "status": "ready-for-navigation",
    "message": "Placeholder router active. Business logic can be added later."
}

@router.get("/")
def get_tasks_checklist_home():
    return {
        "ok": True,
        **MODULE_INFO
    }

@router.get("/meta")
def get_tasks_checklist_meta():
    return {
        **MODULE_INFO
    }

@router.get("/health")
def get_tasks_checklist_health():
    return {
        "ok": True,
        "module": "tasks_checklist"
    }
