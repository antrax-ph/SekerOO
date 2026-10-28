"""HTTP API around the checker engine."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .jobs import JobManager
from .telegram import Telegram

API_TOKEN = os.environ.get("API_TOKEN", "")
OUT_ROOT = Path(os.environ.get("OUT_ROOT", "./ml_results"))
DEFAULT_DEVICES = os.environ.get("DEVICES_FILE")  # optional path
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TG_CHAT  = os.environ.get("TELEGRAM_CHAT")

app = FastAPI(title="ML Checker API", version="1.0.0")
mgr = JobManager(OUT_ROOT)

def auth(authorization: Optional[str] = Header(None)) -> None:
    if not API_TOKEN:
        return  # auth disabled if unset
    expected = f"Bearer {API_TOKEN}"
    if authorization != expected:
        raise HTTPException(401, "unauthorized")

class CheckRequest(BaseModel):
    accounts: list[str] = Field(..., description="list of 'user:pass' strings")
    devices_file: Optional[str] = None
    telegram: bool = False

@app.get("/healthz")
async def healthz():
    return {"ok": True}

@app.post("/check", dependencies=[Depends(auth)])
async def check(req: CheckRequest):
    accounts: list[tuple[str, str]] = []
    for line in req.accounts:
        line = line.strip()
        if not line or ":" not in line:
            continue
        u, p = line.split(":", 1)
        accounts.append((u.strip(), p.strip()))
        
    if not accounts:
        raise HTTPException(400, "no valid user:pass lines")

    tg = Telegram(TG_TOKEN, TG_CHAT) if (req.telegram and TG_TOKEN and TG_CHAT) else None
    
    try:
        job = mgr.create(accounts, devices_file=req.devices_file or DEFAULT_DEVICES, telegram=tg)
        return {"job_id": job.id, "total": job.total}
    except Exception as e:
        # Catch any engine errors para hindi mag-crash ang server
        raise HTTPException(500, f"Failed to start job: {str(e)}")

@app.get("/jobs/{jid}", dependencies=[Depends(auth)])
async def job_status(jid: str):
    job = mgr.get(jid)
    if not job:
        raise HTTPException(404, "job not found")
    return job.snapshot()

@app.post("/jobs/{jid}/stop", dependencies=[Depends(auth)])
async def job_stop(jid: str):
    if not mgr.stop(jid):
        raise HTTPException(404, "job not found")
    return {"stopped": True}

@app.get("/jobs/{jid}/valid_full", dependencies=[Depends(auth)])
async def job_valid_full(jid: str):
    job = mgr.get(jid)
    if not job:
        raise HTTPException(404, "job not found")
    p = OUT_ROOT / jid / "valid_full.txt"
    if not p.exists():
        raise HTTPException(404, "no valid_full.txt yet")
    return FileResponse(p, filename=f"{jid}_valid_full.txt")

@app.get("/jobs/{jid}/valid", dependencies=[Depends(auth)])
async def job_valid(jid: str):
    job = mgr.get(jid)
    if not job:
        raise HTTPException(404, "job not found")
    p = OUT_ROOT / jid / "valid.txt"
    if not p.exists():
        raise HTTPException(404, "no valid.txt yet")
    return FileResponse(p, filename=f"{jid}_valid.txt")