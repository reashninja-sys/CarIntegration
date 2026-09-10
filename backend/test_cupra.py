"""
Run this FIRST to confirm seatconnect can authenticate and fetch battery data.
Works on Windows (your coding PC) and Termux (your phone).

Usage:
    cd backend
    python test_cupra.py
"""
import os
import sys
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── check config ──────────────────────────────────────────────────────────────

print("=" * 54)
print("  Cupra battery API test  (via seatconnect library)")
print("=" * 54)
print()
print("Checking .env …")

def _check(var, secret=False):
    val = os.environ.get(var, "")
    if not val:
        print(f"  ✗  {var}  — NOT SET")
        return None
    display = ("*" * max(0, len(val) - 4) + val[-4:]) if secret else val
    print(f"  ✓  {var} = {display}")
    return val

username = _check("CUPRA_USERNAME")
password = _check("CUPRA_PASSWORD", secret=True)
vin      = _check("CUPRA_VIN")
_check("API_KEY", secret=True)
print()

if not all([username, password, vin]):
    print("Fill in the missing values in .env and re-run.")
    sys.exit(1)

# ── run test ──────────────────────────────────────────────────────────────────

from cupra_api import CupraClient, CupraAuthError, CupraAPIError

client = CupraClient(username, password, vin)

print("Connecting to Cupra (seatconnect) … this takes a few seconds …")
print()
t0 = time.time()

try:
    data = client.get_battery_status()
except CupraAuthError as e:
    print(f"  ✗  Authentication failed: {e}")
    print()
    print("Common causes:")
    print("  • Wrong email or password")
    print("  • Two-factor auth enabled — disable it in the MyCupra app")
    print("  • VW Group API change — check https://github.com/rennecd/python-seatconnect")
    sys.exit(1)
except CupraAPIError as e:
    print(f"  ✗  API error: {e}")
    sys.exit(1)

elapsed = time.time() - t0
print(f"  ✓  Done in {elapsed:.1f}s")
print()
print(f"  Battery level  : {data['battery_level']} %")
print(f"  Electric range : {data['range_km']} km")
print(f"  Charging       : {data['charging']}")
if data['time_to_full'] is not None:
    print(f"  Time to full   : {data['time_to_full']} min")
print()
print("=" * 54)
print("  All good — run:  python server.py")
print("=" * 54)
