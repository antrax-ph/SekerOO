#!/usr/bin/env python3
from __future__ import annotations
import argparse
import asyncio
import sys
from pathlib import Path

from .engine import Engine


def read_combolist(path: Path) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or ":" not in line: continue
            a, b = line.split(":", 1)
            out.append((a.strip(), b.strip()))
    return out


def main() -> int:
    ap = argparse.ArgumentParser("ml_checker")
    ap.add_argument("combolist", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=Path("./ml_results"))
    ap.add_argument("--devices", type=str, default=None)
    ap.add_argument("--telegram-token", type=str, default=None)
    ap.add_argument("--telegram-chat",  type=str, default=None)
    args = ap.parse_args()

    accounts = read_combolist(args.combolist)
    if not accounts:
        print("no valid lines", file=sys.stderr); return 2

    tg = None
    if args.telegram_token and args.telegram_chat:
        from .telegram import Telegram
        tg = Telegram(args.telegram_token, args.telegram_chat)

    engine = Engine(accounts, args.out, telegram=tg, devices_file=args.devices)
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        engine.stop(); print("\ninterrupted")
    return 0


if __name__ == "__main__":
    sys.exit(main())