"""
Cupra battery API client — powered by the seatconnect community library.
https://github.com/rennecd/python-seatconnect

seatconnect handles all VW Group OAuth complexity and keeps pace with
API/endpoint changes so we don't have to.

The library is async; CupraClient exposes a plain synchronous interface
that Flask can call directly with asyncio.run().
"""

import sys
import asyncio
import logging
from typing import Dict, Any, Optional

import aiohttp
from seatconnect import Connection
from seatconnect.exceptions import (
    SeatException,
    SeatAuthenticationException,
    SeatLoginFailedException,
    SeatAccountLockedException,
)

# aiohttp on Windows needs SelectorEventLoop (not the default ProactorEventLoop)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logger = logging.getLogger(__name__)


class CupraAuthError(Exception):
    pass


class CupraAPIError(Exception):
    pass


async def _fetch_battery(username: str, password: str, vin: str) -> Dict[str, Any]:
    """
    Full async flow: login → get vehicles → update → return battery data.
    A new aiohttp session is created each call; seatconnect manages token refresh
    internally so this is safe to call as often as needed.
    """
    async with aiohttp.ClientSession() as session:
        conn = Connection(session, username, password)

        try:
            ok = await conn.doLogin()
        except (SeatAuthenticationException, SeatLoginFailedException, SeatAccountLockedException) as e:
            raise CupraAuthError(str(e)) from e
        except SeatException as e:
            raise CupraAuthError(f"Login error: {e}") from e

        if not ok:
            raise CupraAuthError(
                "Login returned false. Check your email/password, "
                "and make sure two-factor auth is disabled in the MyCupra app."
            )

        await conn.get_vehicles()

        vehicle = conn.vehicle(vin)
        if vehicle is None:
            available = [v.unique_id for v in conn.vehicles]
            raise CupraAPIError(
                f"VIN {vin!r} not found on this account. "
                f"VINs returned: {available or '(none — check account)'}"
            )

        await vehicle.update()

        # Pull values with supported-flag guards so we get None rather than
        # an AttributeError if this vehicle type doesn't support a field.
        battery_level: Optional[int] = (
            vehicle.battery_level if vehicle.is_battery_level_supported else None
        )
        electric_range: Optional[int] = (
            vehicle.electric_range if vehicle.is_electric_range_supported else None
        )
        charging: bool = bool(
            vehicle.charging if vehicle.is_charging_supported else False
        )
        time_to_full: Optional[int] = (
            vehicle.charging_time_left if vehicle.is_charging_time_left_supported else None
        )

        logger.info(
            "seatconnect: battery=%s%%  range=%skm  charging=%s  time_to_full=%smin",
            battery_level, electric_range, charging, time_to_full,
        )

        return {
            "battery_level": battery_level,
            "range_km":      electric_range,
            "charging":      charging,
            "time_to_full":  time_to_full,   # minutes; None if not charging
            "charging_state": None,           # not exposed by seatconnect directly
        }


class CupraClient:
    """Synchronous wrapper — drop-in replacement for the old hand-rolled client."""

    def __init__(self, username: str, password: str, vin: str):
        self.username = username
        self.password = password
        self.vin      = vin

    def get_battery_status(self) -> Dict[str, Any]:
        """Fetch live battery data. Blocks until complete (typically 3-8 s)."""
        try:
            return asyncio.run(
                _fetch_battery(self.username, self.password, self.vin)
            )
        except (CupraAuthError, CupraAPIError):
            raise
        except Exception as exc:
            raise CupraAPIError(f"Unexpected error: {exc}") from exc
