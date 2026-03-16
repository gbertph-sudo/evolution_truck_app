from fastapi import APIRouter

router = APIRouter(
    prefix="/api/quotes",
    tags=["Estimates / Quotes"]
)

@router.get("/")
def get_quotes_root():
    return {
        "ok": True,
        "module": "quotes",
        "title": "Estimates / Quotes",
        "status": "placeholder",
        "message": "Module scaffold ready. Business logic can be implemented later."
    }
