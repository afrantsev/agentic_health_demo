import logging

from fastapi import FastAPI, HTTPException

from .crew import run_briefing
from .schemas import BriefingRequest, BriefingResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Condition Briefing API")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# Sync handler on purpose: FastAPI runs it in a worker thread, so the blocking crew run
# doesn't stall the event loop.
@app.post("/api/briefing", response_model=BriefingResponse)
def create_briefing(req: BriefingRequest) -> BriefingResponse:
    condition = req.condition.strip()
    try:
        return run_briefing(condition)
    except Exception as exc:
        logger.exception("Briefing failed for %r", condition)
        raise HTTPException(status_code=502, detail=f"Briefing generation failed: {exc}") from exc
