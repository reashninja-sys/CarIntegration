"""
HTTP server the Garmin widget polls for Cupra battery data.

Binds to 0.0.0.0 so Garmin Connect Mobile's HTTP proxy can reach it
whether it resolves via localhost or the phone's LAN IP.
API key is the security layer — every request without it gets a 403.

Run:  python server.py
"""

import os
import time
import socket
import logging
import threading
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, jsonify, request, abort

from cupra_api import CupraClient, CupraAuthError, CupraAPIError

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

USERNAME  = os.environ["CUPRA_USERNAME"]
PASSWORD  = os.environ["CUPRA_PASSWORD"]
VIN       = os.environ["CUPRA_VIN"]
API_KEY   = os.environ["API_KEY"]
CACHE_TTL = int(os.environ.get("CACHE_TTL", "300"))   # seconds; default 5 min
PORT      = int(os.environ.get("PORT", "5000"))
BIND_HOST = os.environ.get("BIND_HOST", "0.0.0.0")

_client = CupraClient(USERNAME, PASSWORD, VIN)
_cache: dict = {
    "battery_level":  None,
    "range_km":       None,
    "charging":       False,
    "time_to_full":   None,
    "last_updated":   "--:--",
    "last_fetch":     0.0,
    "error":          None,
}
_lock = threading.Lock()


# ── security ──────────────────────────────────────────────────────────────────

@app.before_request
def check_api_key() -> None:
    if request.path in ("/ping", "/health"):
        return
    if request.headers.get("X-Api-Key") != API_KEY:
        logger.warning("Rejected — bad/missing key from %s", request.remote_addr)
        abort(403)


# ── data ──────────────────────────────────────────────────────────────────────

def _fetch() -> None:
    data = _client.get_battery_status()
    with _lock:
        _cache.update(
            battery_level=data["battery_level"],
            range_km=data["range_km"],
            charging=data["charging"],
            time_to_full=data["time_to_full"],
            last_updated=datetime.now().strftime("%H:%M"),
            last_fetch=time.time(),
            error=None,
        )
    logger.info(
        "Battery %s%%  range %skm  charging=%s",
        data["battery_level"], data["range_km"], data["charging"],
    )


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.route("/ping")
def ping():
    """No auth. Open in your phone browser to confirm the server is reachable."""
    return jsonify({"ok": True, "server": "cupra-battery"})


@app.route("/health")
def health():
    """No auth. Returns cache age."""
    with _lock:
        age = time.time() - _cache["last_fetch"]
    return jsonify({"status": "ok", "cache_age_s": round(age)})


@app.route("/battery")
def battery():
    """Main endpoint polled by the Garmin widget."""
    with _lock:
        stale = time.time() - _cache["last_fetch"] > CACHE_TTL

    if stale:
        try:
            _fetch()
        except (CupraAuthError, CupraAPIError) as exc:
            logger.error("Cupra error: %s", exc)
            with _lock:
                _cache["error"] = str(exc)
        except Exception as exc:
            logger.exception("Unexpected error fetching battery data")
            with _lock:
                _cache["error"] = str(exc)

    with _lock:
        if _cache["error"] and _cache["battery_level"] is None:
            return jsonify({"error": _cache["error"]}), 503

        return jsonify({
            "battery_level": _cache["battery_level"] or 0,
            "range_km":      _cache["range_km"],
            "charging":      _cache["charging"],
            "time_to_full":  _cache["time_to_full"],
            "last_updated":  _cache["last_updated"],
        })


@app.route("/refresh")
def refresh():
    """Force a fresh Cupra API call (useful for testing from browser)."""
    try:
        _fetch()
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    with _lock:
        return jsonify({"battery_level": _cache["battery_level"], "ok": True})


# ── startup ───────────────────────────────────────────────────────────────────

def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "YOUR_PHONE_IP"


if __name__ == "__main__":
    logger.info("Initial Cupra fetch via seatconnect …")
    try:
        _fetch()
    except Exception as exc:
        logger.warning("Initial fetch failed (will retry on first request): %s", exc)

    lan_ip = _lan_ip()
    print()
    print("=" * 54)
    print("  Cupra battery server running")
    print()
    print("  ➜  Garmin Connect widget settings — Server URL:")
    print(f"     http://{lan_ip}:{PORT}")
    print()
    print("  ➜  Test from phone browser (no key needed):")
    print(f"     http://{lan_ip}:{PORT}/ping")
    print("=" * 54)
    print()

    app.run(host=BIND_HOST, port=PORT, debug=False)
