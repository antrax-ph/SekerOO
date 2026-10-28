"""Background job manager for the API."""
from __future__ import annotations
import asyncio
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .engine import Engine


@dataclass
class Job:
    id: str
    accounts: list[tuple[str, str]]
    status: str = "queued"          # queued | running | done | stopped | error
    total: int = 0
    processed: int = 0
    valid: int = 0
    invalid: int = 0
    errors: int = 0
    results: list[dict] = field(default_factory=list)
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    engine: Optional[Engine] = None
    task: Optional[asyncio.Task] = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "total": self.total,
            "processed": self.processed,
            "valid": self.valid,
            "invalid": self.invalid,
            "errors": self.errors,
            "results": self.results,
            "error": self.error,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }


class JobManager:
    def __init__(self, out_root: Path):
        self.out_root = out_root
        self.out_root.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, Job] = {}

    def create(self, accounts: list[tuple[str, str]],
               devices_file: Optional[str] = None,
               telegram=None) -> Job:
        jid = uuid.uuid4().hex[:12]
        out_dir = self.out_root / jid
        eng = Engine(accounts, out_dir, telegram=telegram,
                     devices_file=devices_file, notify=self._make_notify(jid))
        job = Job(id=jid, accounts=accounts, total=len(accounts), engine=eng)
        self._jobs[jid] = job
        job.task = asyncio.create_task(self._run(job))
        return job

    def _make_notify(self, jid: str):
        def notify(event: dict) -> None:
            job = self._jobs.get(jid)
            if not job:
                return
            t = event.get("type")
            if t == "start":
                job.status = "running"
            elif t == "account_done":
                job.processed += 1
                if event.get("label") == "VALID":
                    job.valid += 1
                    job.results.append(event)
                elif event.get("label") == "INVALID":
                    job.invalid += 1
                else:
                    job.errors += 1
            elif t == "error":
                job.errors += 1
            elif t == "done":
                job.status = "stopped" if event.get("stopped") else "done"
                job.finished_at = time.time()
        return notify

    async def _run(self, job: Job) -> None:
        try:
            await job.engine.run()
        except asyncio.CancelledError:
            job.status = "stopped"
            job.finished_at = time.time()
            raise
        except Exception as e:
            job.status = "error"
            job.error = f"{type(e).__name__}: {e}"
            job.finished_at = time.time()

    def get(self, jid: str) -> Optional[Job]:
        return self._jobs.get(jid)

    def stop(self, jid: str) -> bool:
        job = self._jobs.get(jid)
        if not job:
            return False
        job.engine.stop()
        return True

    async def shutdown(self) -> None:
        for job in self._jobs.values():
            if job.task and not job.task.done():
                job.engine.stop()
                try:
                    await asyncio.wait_for(job.task, timeout=10)
                except Exception:
                    job.task.cancel()