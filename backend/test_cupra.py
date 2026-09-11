"""
Standalone diagnostic — run this BEFORE starting server.py.

Usage:
    cd C:\\Users\\daveb\\CarIntegration\\backend
    python test_cupra.py

This no longer needs seatconnect; uses our own OAuth2 flow.
"""

import os
import sys
import logging

# Verbose logging so we can see every step
logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)s  %(name)s  %(message)s",
)

# Suppress chatty noise from aiohttp internals
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

from pathlib import Path
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)
    print(f"✓ Loaded .env from {env_path}")
else:
    print(f"✗ .env not found at {env_path}")
    print("  Copy .env.example to .env and fill in your credentials.")
    sys.exit(1)

username = os.getenv("CUPRA_USERNAME", "")
password = os.getenv("CUPRA_PASSWORD", "")
vin      = os.getenv("CUPRA_VIN", "")

if not all([username, password, vin]):
    missing = [k for k, v in [
        ("CUPRA_USERNAME", username),
        ("CUPRA_PASSWORD", password),
        ("CUPRA_VIN",      vin),
    ] if not v]
    print(f"✗ Missing in .env: {', '.join(missing)}")
    sys.exit(1)

print(f"\n→ Username : {username}")
print(f"→ VIN      : {vin}")
print(f"→ Password : {'*' * len(password)}")
print("\n⏳  Authenticating… (this takes 10-30 s)\n")

from cupra_api import CupraClient, CupraAuthError, CupraAPIError

try:
    client = CupraClient(username, password, vin)
    data   = client.get_battery_status()

    print("\n" + "=" * 50)
    print("✓ SUCCESS")
    print("=" * 50)
    print(f"  Battery : {data['battery_level']} %")
    print(f"  Range   : {data['range_km']} km")
    print(f"  Charging: {data['charging']}")
    if data.get("time_to_full"):
        print(f"  To full : {data['time_to_full']} min")
    print("=" * 50)

except CupraAuthError as e:
    print(f"\n✗ AUTH ERROR: {e}")
    print("\nCommon causes:")
    print("  • Wrong username / password in .env")
    print("  • 2FA enabled — disable it in the MyCupra app (Profile → Security)")
    print("  • Account locked — try logging in via browser to unlock")
    sys.exit(1)

except CupraAPIError as e:
    print(f"\n✗ API ERROR: {e}")
    print("\nAuthentication worked but failed to get vehicle data.")
    print("Check that your VIN is correct.")
    sys.exit(1)

except Exception as e:
    print(f"\n✗ UNEXPECTED ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
