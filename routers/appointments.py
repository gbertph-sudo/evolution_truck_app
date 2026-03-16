from fastapi import APIRouter

router = APIRouter(
    prefix="/api/appointments",
    tags=["Appointments"]
)

@router.get("/")
def get_appointments_root():
    return {
        "ok": True,
        "module": "appointments",
        "title": "Appointments",
        "status": "placeholder",
        "message": "Module scaffold ready. Business logic can be implemented later."
    }
