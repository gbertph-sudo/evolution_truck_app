from fastapi import APIRouter

router = APIRouter(
    prefix="/api/tasks",
    tags=["Tasks / Checklist"]
)

@router.get("/")
def get_tasks_root():
    return {
        "ok": True,
        "module": "tasks",
        "title": "Tasks / Checklist",
        "status": "placeholder",
        "message": "Module scaffold ready. Business logic can be implemented later."
    }
