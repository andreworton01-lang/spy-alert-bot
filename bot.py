import os
import sys
import smtplib
from email.message import EmailMessage
from datetime import datetime, timezone
import requests

# ---- CONFIG (set via Railway Variables) ----
ALPACA_KEY_ID = os.getenv("ALPACA_KEY_ID", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")  # paper by default
TO_EMAIL = os.getenv("ALERT_TO_EMAIL", "")
FROM_EMAIL = os.getenv("ALERT_FROM_EMAIL", "")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")

SYMBOL = os.getenv("SYMBOL", "SPY")
MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY", "1"))

# Trading window (Central) converted to UTC for the cron schedule:
# 08:35–10:00 CT == 14:35–16:00 UTC when CT is UTC-6 (standard time).
# (We enforce this window again here as a safety belt.)
WINDOW_START_UTC = os.getenv("WINDOW_START_UTC", "14:35")
WINDOW_END_UTC = os.getenv("WINDOW_END_UTC", "16:00")

# Mode: "DRY_RUN" sends predictable test alerts; "LIVE" uses simple rule stub.
MODE = os.getenv("MODE", "DRY_RUN")  # DRY_RUN or LIVE

# ---- Helpers ----
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def hhmm_to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)

def in_window_utc(dt: datetime) -> bool:
    t = dt.hour * 60 + dt.minute
    return hhmm_to_minutes(WINDOW_START_UTC) <= t <= hhmm_to_minutes(WINDOW_END_UTC)

def alpaca_headers() -> dict:
    return {
        "APCA-API-KEY-ID": ALPACA_KEY_ID,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
    }

def alpaca_get(path: str, params: dict | None = None) -> dict:
    url = f"{ALPACA_BASE_URL.rstrip('/')}{path}"
    r = requests.get(url, headers=alpaca_headers(), params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def get_open_position_qty(symbol: str) -> int:
    try:
        pos = alpaca_get(f"/v2/positions/{symbol}")
        # Alpaca returns qty as string
        return int(float(pos.get("qty", "0")))
    except requests.HTTPError as e:
        # 404 means no position
        if e.response is not None and e.response.status_code == 404:
            return 0
        raise

def send_email(subject: str, body: str) -> None:
    if not (TO_EMAIL and FROM_EMAIL and SMTP_HOST and SMTP_USER and SMTP_PASS):
        print("Missing email/SMTP env vars; cannot send.", file=sys.stderr)
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = FROM_EMAIL
    msg["To"] = TO_EMAIL
    msg.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)

def buy_alert(qty: int) -> tuple[str, str]:
    subj = "BUY SPY — ACTION REQUIRED"
    body = f"""BUY {SYMBOL} NOW
Qty: {qty}
Order: Market
Max Risk: $50 (paper)

Open Alpaca and BUY within 5 minutes.
"""
    return subj, body

def sell_alert(qty: int, reason: str) -> tuple[str, str]:
    subj = "SELL SPY — ACTION REQUIRED"
    body = f"""SELL {SYMBOL} NOW
Qty: {qty}
Reason: {reason}

Open Alpaca and SELL immediately.
"""
    return subj, body

# ---- Decision Logic (simple + safe scaffolding) ----
def decide_and_notify():
    dt = now_utc()
    if not in_window_utc(dt):
        print("Outside window; exiting.")
        return

    qty_open = get_open_position_qty(SYMBOL)

    # DRY_RUN mode:
    # - If no position: send a BUY at a predictable minute (e.g., :40)
    # - If position: send a SELL at a predictable minute (e.g., :55)
    if MODE.upper() == "DRY_RUN":
        if qty_open == 0 and dt.minute in (40,):
            subj, body = buy_alert(qty=1)
            send_email(subj, body)
            print("Sent DRY_RUN BUY.")
        elif qty_open > 0 and dt.minute in (55,):
            subj, body = sell_alert(qty=qty_open, reason="DRY_RUN exit")
            send_email(subj, body)
            print("Sent DRY_RUN SELL.")
        else:
            print("DRY_RUN: no message this minute.")
        return

    # LIVE mode stub (placeholder):
    # If no position, we do NOTHING unless you later approve a real strategy.
    # If you do have a position, we still do NOTHING until we implement exit logic.
    print("LIVE: strategy not enabled; no alerts.")

if __name__ == "__main__":
    decide_and_notify()
