#!/usr/bin/env python3
"""Daily gapbf health-check + progress ping to a Telegram bot.

Reads progress straight from the sqlite DB and posts a summary.
Stdlib only (sqlite3 + urllib) so it runs on the bare server python3.

Env (injected live by `infisical run` via run_healthcheck.sh):
  TELEGRAM_RS_AUTOMATION_BOT_TOKEN   required  -- bot token from infisical
  TELEGRAM_RS_AUTOMATION_CHAT_ID     required  -- destination chat id
  GAPBF_DB                           optional  -- default ~/.gapbf/gapbf.db
  GAPBF_STALE_MIN                    optional  -- liveness threshold, default 60 min
(TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID accepted as fallbacks.)
"""
import json
import os
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone

DB = os.path.expanduser(os.environ.get("GAPBF_DB", "~/.gapbf/gapbf.db"))
STALE_MIN = int(os.environ.get("GAPBF_STALE_MIN", "60"))
TOKEN = (os.environ.get("TELEGRAM_RS_AUTOMATION_BOT_TOKEN")
         or os.environ.get("TELEGRAM_BOT_TOKEN", ""))
CHAT_ID = (os.environ.get("TELEGRAM_RS_AUTOMATION_CHAT_ID")
           or os.environ.get("TELEGRAM_CHAT_ID", ""))


def _parse(ts):
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def collect():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    q1 = lambda sql: c.execute(sql).fetchone()
    total = q1("SELECT COUNT(*) FROM attempts")[0]
    distinct = q1("SELECT COUNT(DISTINCT attempt) FROM attempts")[0]
    by_result = c.execute(
        "SELECT result_classification, COUNT(*) FROM attempts "
        "GROUP BY 1 ORDER BY 2 DESC"
    ).fetchall()
    run = q1(
        "SELECT status, grid_size, started_at, updated_at "
        "FROM runs ORDER BY updated_at DESC LIMIT 1"
    )
    last_ts = q1("SELECT MAX(timestamp) FROM attempts")[0]
    # attempts in the last 24h -- lexicographic compare works on ISO-8601 UTC
    cutoff = datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() - 86400, timezone.utc
    ).isoformat()
    last24 = c.execute(
        "SELECT COUNT(*) FROM attempts WHERE timestamp >= ?", (cutoff,)
    ).fetchone()[0]
    c.close()
    return {
        "total": total, "distinct": distinct, "by_result": by_result,
        "run": run, "last_ts": last_ts, "last24": last24,
    }


def _age(ts, now):
    t = _parse(ts)
    if t is None:
        return None, "never"
    mins = (now - t).total_seconds() / 60
    if mins < 90:
        return mins, f"{mins:.0f} min ago"
    if mins < 60 * 48:
        return mins, f"{mins / 60:.1f} h ago"
    return mins, f"{mins / 1440:.1f} d ago"


def build_message(d):
    run = d["run"]
    status = run[0] if run else "none"
    grid = run[1] if run else "?"
    updated = run[3] if run else None
    now = datetime.now(timezone.utc)
    # liveness = process heartbeat (runs.updated_at), NOT last attempt:
    # the grid may be fully swept yet the worker still running/idling.
    beat_min, beat_txt = _age(updated, now)
    alive = status == "running" and beat_min is not None and beat_min <= STALE_MIN
    _, attempt_txt = _age(d["last_ts"], now)
    head = "✅ gapbf RUNNING" if alive else "⚠️ gapbf CHECK IT"
    results = "\n".join(f"  • {k or 'unknown'}: {v:,}" for k, v in d["by_result"])
    return (
        f"{head}\n"
        f"date: {now:%Y-%m-%d %H:%M} UTC\n"
        f"latest run: {status} (grid {grid}), heartbeat {beat_txt}\n"
        f"attempts total: {d['total']:,} ({d['distinct']:,} distinct)\n"
        f"last new attempt: {attempt_txt}\n"
        f"last 24h: +{d['last24']:,}\n"
        f"by result:\n{results}"
    )


def send(text):
    if not TOKEN or not CHAT_ID:
        sys.exit("bot token / chat id not set -- expected TELEGRAM_RS_AUTOMATION_* "
                 "injected by `infisical run` (see run_healthcheck.sh)")
    data = json.dumps({"chat_id": CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data=data, headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        sys.exit(f"telegram HTTP {e.code}: {detail}")
    if not body.get("ok"):
        sys.exit(f"telegram error: {body}")


def main():
    msg = build_message(collect())
    print(msg)
    send(msg)
    print("sent ok")


if __name__ == "__main__":
    main()
