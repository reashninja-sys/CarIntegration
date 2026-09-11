"""
Cupra battery API client.

Authentication flow:
1. VW Group OAuth2 hybrid flow (code+id_token+token) via identity.vwgroup.io
2. Token exchange at tokenrefreshservice.apps.emea.vwapps.io/exchangeAuthCode
   → returns a bearer token accepted by the Cupra OLA API
3. GET https://ola.prod.code.seat.cloud.vwgroup.com/v2/users/{userId}/garage/vehicles

Step 2 (tokenrefreshservice) may return 503 when:
- Called from non-mobile IP addresses (it's used by the Cupra mobile app)
- Service is temporarily under maintenance

It consistently works from the Android phone (Termux) on mobile or home WiFi.
"""

import re
import sys
import json
import asyncio
import logging
import secrets
from typing import Dict, Any, Optional
from urllib.parse import urlencode
import base64

import aiohttp

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logger = logging.getLogger(__name__)

CUPRA_CLIENT_ID = "30e33736-c537-4c72-ab60-74a7b92cfe83@apps_vw-dilab_com"
CUPRA_REDIRECT  = "cupraconnect://identity-kit/login"
CUPRA_SCOPE     = ("openid profile address phone email birthdate "
                   "nationalIdentifier cars mbb dealers badge nationality")
CUPRA_RESP_TYPE = "code id_token token"
IDENTITY        = "https://identity.vwgroup.io"
OLA_API         = "https://ola.prod.code.seat.cloud.vwgroup.com"
TOKEN_EXCHANGE  = "https://tokenrefreshservice.apps.emea.vwapps.io/exchangeAuthCode"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=40)

APP_HEADERS = {
    "User-Agent":     "okhttp/3.10.0",
    "X-App-Name":     "CUPRAconnect",
    "X-App-Version":  "1.0.0",
    "X-Brand":        "CUPRA",
}


class CupraAuthError(Exception):
    pass


class CupraAPIError(Exception):
    pass


# ── HTML / JWT helpers ────────────────────────────────────────────────────────

def _hidden_fields(html: str) -> Dict[str, str]:
    """Hidden form fields as dict (last value wins)."""
    fields: Dict[str, str] = {}
    for tag in re.findall(r'<input[^>]+type=["\']hidden["\'][^>]*>', html, re.I):
        name  = re.search(r'\bname=["\']([^"\']+)["\']',  tag)
        value = re.search(r'\bvalue=["\']([^"\']*)["\']', tag)
        if name:
            fields[name.group(1)] = value.group(1) if value else ""
    return fields


def _hidden_fields_list(html: str):
    """Hidden form fields as list-of-tuples (preserves duplicate names)."""
    pairs = []
    for tag in re.findall(r'<input[^>]+type=["\']hidden["\'][^>]*>', html, re.I):
        name  = re.search(r'\bname=["\']([^"\']+)["\']',  tag)
        value = re.search(r'\bvalue=["\']([^"\']*)["\']', tag)
        if name:
            pairs.append((name.group(1), value.group(1) if value else ""))
    return pairs


def _template_model(html: str) -> Optional[Dict]:
    """Extract nested templateModel JSON from VW Group pages."""
    idx = html.find("templateModel:")
    if idx < 0:
        idx = html.find('"templateModel"')
    if idx < 0:
        return None
    start = html.find("{", idx)
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(html)):
        if html[i] == "{":
            depth += 1
        elif html[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _csrf_token(html: str) -> str:
    m = re.search(r"csrf_token\s*:\s*['\"]([^'\"]+)['\"]", html)
    return m.group(1) if m else ""


def _find_in_url(url_or_text: str, param: str) -> Optional[str]:
    m = re.search(rf'[?&#]{re.escape(param)}=([^&"\'#\s]+)', url_or_text)
    return m.group(1) if m else None


def _decode_jwt_payload(token: str) -> Dict:
    try:
        seg = token.split(".")[1]
        seg += "=" * (4 - len(seg) % 4)
        return json.loads(base64.urlsafe_b64decode(seg))
    except Exception:
        return {}


# ── OAuth flow ────────────────────────────────────────────────────────────────

async def _login(session: aiohttp.ClientSession, username: str, password: str) -> Dict[str, Optional[str]]:
    """
    Complete VW Group OAuth2 hybrid flow.
    Returns dict with keys: code, access_token, id_token, user_id.
    """
    state = secrets.token_urlsafe(16)
    nonce = secrets.token_urlsafe(16)

    auth_headers = {
        "User-Agent":       "okhttp/3.10.0",
        "Accept":           "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language":  "en-GB,en;q=0.9",
        "x-requested-with": "SEATConnect",
    }

    # Step 1: get email form
    auth_url = (f"{IDENTITY}/oidc/v1/authorize?" + urlencode({
        "client_id":     CUPRA_CLIENT_ID,
        "redirect_uri":  CUPRA_REDIRECT,
        "response_type": CUPRA_RESP_TYPE,
        "scope":         CUPRA_SCOPE,
        "state":         state,
        "nonce":         nonce,
    }))
    resp = await session.get(auth_url, allow_redirects=True, headers=auth_headers)
    html = await resp.text()
    form = _hidden_fields(html)
    if not form:
        raise CupraAuthError("No login form on VW Group page — API may have changed.")

    # Step 2: submit email → password page (303 redirect)
    form["email"] = username
    form["registerFlow"] = "false"
    resp = await session.post(
        f"{IDENTITY}/signin-service/v1/{CUPRA_CLIENT_ID}/login/identifier",
        data=form, allow_redirects=True, headers=auth_headers,
    )
    html = await resp.text()

    # Step 3: extract hmac + relayState + CSRF from password page
    tm = _template_model(html)
    pw_form: Dict[str, str] = {}
    if tm:
        pw_form["hmac"]       = tm.get("hmac") or ""
        pw_form["relayState"] = tm.get("relayState") or ""
    else:
        pw_form = _hidden_fields(html)
        logger.warning("No templateModel on password page — using hidden fields")

    csrf = _csrf_token(html)
    if csrf:
        pw_form["_csrf"] = csrf
    pw_form["email"]        = username
    pw_form["password"]     = password
    pw_form["registerFlow"] = "false"

    auth_action = f"{IDENTITY}/signin-service/v1/{CUPRA_CLIENT_ID}/login/authenticate"
    if tm and tm.get("postAction"):
        act = tm["postAction"]
        if not act.startswith("http"):
            act = f"{IDENTITY}/signin-service/v1/{CUPRA_CLIENT_ID}/{act}"
        auth_action = act

    # Step 4: submit password — follow the entire redirect chain.
    # The chain ends at cupraconnect:// which aiohttp cannot connect to
    # and raises ValueError/InvalidURL.  We catch ALL exceptions and look
    # for the cupraconnect:// URL in the exception message.
    cb: Dict[str, Optional[str]] = {"code": None, "access_token": None, "id_token": None}

    def _parse(url_str: str):
        if "cupraconnect://" not in url_str:
            return
        cb["code"]         = _find_in_url(url_str, "code")
        cb["access_token"] = _find_in_url(url_str, "access_token")
        cb["id_token"]     = _find_in_url(url_str, "id_token")

    try:
        resp = await session.post(
            auth_action, data=pw_form,
            allow_redirects=True, headers=auth_headers,
        )
        final_url = str(resp.url)

        if "cupraconnect://" in final_url:
            _parse(final_url)
        elif "/consent/" in final_url:
            html = await resp.text()
            tok = await _handle_consent(session, resp, html, auth_headers)
            if tok:
                _parse(tok if "cupraconnect://" in tok else f"cupraconnect://#code={tok}")
        else:
            html = await resp.text()
            tm2  = _template_model(html)
            tmpl = (tm2 or {}).get("template", "unknown")
            if "wrong" in html[:500].lower() or "incorrect" in html[:500].lower():
                raise CupraAuthError("Wrong username or password.")
            raise CupraAuthError(
                f"OAuth stopped at {final_url!r} (template={tmpl!r}). "
                "See debug_auth_result.html for details."
            )

    except CupraAuthError:
        raise
    except Exception as exc:
        _parse(str(exc))
        if not any(cb.values()):
            raise CupraAuthError(f"Unexpected error in auth redirect: {exc}") from exc

    if not any(cb.values()):
        raise CupraAuthError(
            "Auth completed but no tokens in callback. "
            "Try logging out of MyCupra app and back in."
        )

    # Decode user_id from id_token sub claim
    user_id = ""
    if cb["id_token"]:
        payload = _decode_jwt_payload(cb["id_token"])
        user_id = payload.get("sub", "")

    logger.info("Auth OK — user_id=%s  code=%s  access_token=%s  id_token=%s",
                user_id, bool(cb["code"]), bool(cb["access_token"]), bool(cb["id_token"]))
    cb["user_id"] = user_id
    return cb


async def _handle_consent(
    session: aiohttp.ClientSession,
    resp: aiohttp.ClientResponse,
    html: str,
    headers: dict,
) -> Optional[str]:
    """Auto-submit VW Group consent form (appears on first use)."""
    logger.info("Consent page — auto-submitting (%s)", resp.url)
    pairs = _hidden_fields_list(html)
    csrf  = _csrf_token(html)
    if csrf and not any(k == "_csrf" for k, _ in pairs):
        pairs.append(("_csrf", csrf))

    action_url = str(resp.url)
    m = re.search(r'<form[^>]+action=["\']([^"\']+)["\']', html, re.I)
    if m:
        action_url = m.group(1).replace("&amp;", "&")
        if not action_url.startswith("http"):
            action_url = f"{IDENTITY}{action_url}"

    logger.info("Consent POST → %s  fields=%s", action_url, [k for k, _ in pairs])
    try:
        r = await session.post(action_url, data=pairs, allow_redirects=True, headers=headers)
        return str(r.url)
    except Exception as exc:
        url_str = str(exc)
        return url_str if "cupraconnect://" in url_str else None


# ── Token exchange ────────────────────────────────────────────────────────────

async def _get_ola_token(
    session: aiohttp.ClientSession,
    cb: Dict[str, Optional[str]],
) -> str:
    """
    Exchange VW Group OAuth tokens for an OLA API bearer token.

    The tokenrefreshservice is used by the Cupra mobile app and is accessible
    from phone networks.  It may return 503 from desktop/server IPs.
    """
    code     = cb.get("code")
    id_token = cb.get("id_token")
    direct   = cb.get("access_token") or cb.get("id_token") or ""

    if not (code and id_token):
        logger.warning("Missing code or id_token — skipping exchange")
        return direct

    exchange_headers = {
        **APP_HEADERS,
        "Content-Type":  "application/json",
        "Accept":        "application/json",
        "Authorization": f"Bearer {id_token}",
    }

    for brand in ("seat", "cupra"):
        logger.info("Trying tokenrefreshservice (brand=%s)…", brand)
        try:
            resp = await session.post(
                TOKEN_EXCHANGE,
                json={"auth_code": code, "id_token": id_token, "brand": brand},
                headers=exchange_headers,
            )
            body = await resp.text()
            logger.debug("Token exchange %s → %s  body=%s", brand, resp.status, body[:200])

            if resp.ok and body.strip().startswith("{"):
                data = json.loads(body)
                tok  = data.get("accessToken") or data.get("access_token")
                if tok:
                    logger.info("Got OLA API token ✓")
                    return tok

            if resp.status == 503:
                logger.warning(
                    "tokenrefreshservice returned 503. "
                    "This service is used by the Cupra mobile app and may only be "
                    "reachable from phone networks.  Run from Termux on your phone."
                )
                break  # same error for both brands — don't retry

        except Exception as exc:
            logger.warning("Token exchange failed: %s", exc)

    # Fall back to whatever token we have (will get 403 from OLA API on desktop;
    # may work differently from Termux depending on server-side validation)
    logger.warning("Token exchange failed — using fallback token from OAuth callback")
    return direct


# ── Vehicle data ──────────────────────────────────────────────────────────────

async def _fetch_battery(username: str, password: str, vin: str) -> Dict[str, Any]:
    """Authenticate and fetch battery data."""
    async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
        cb        = await _login(session, username, password)
        ola_token = await _get_ola_token(session, cb)
        user_id   = cb.get("user_id", "")

        api_headers = {
            **APP_HEADERS,
            "Authorization": f"Bearer {ola_token}",
            "Accept":        "application/json",
            "Content-Type":  "application/json",
        }

        # Prefer user-specific garage endpoint (most reliable path)
        candidates = []
        if user_id:
            candidates += [
                f"{OLA_API}/v2/users/{user_id}/garage/vehicles",
                f"{OLA_API}/v1/users/{user_id}/vehicles",
            ]
        candidates += [
            f"{OLA_API}/v1/vehicles",
            f"{OLA_API}/v2/vehicles",
            f"{OLA_API}/v1/users/vehicles",
        ]

        vehicles_payload = None
        last_status, last_body = 0, ""
        for url in candidates:
            try:
                resp = await session.get(url, headers=api_headers)
                body = await resp.text()
                logger.debug("vehicle-list %s → %s", url, resp.status)
                if resp.status == 200 and body.strip().startswith(("{", "[")):
                    vehicles_payload = json.loads(body)
                    logger.info("Vehicle list from %s: %s", url, body[:200])
                    break
                elif resp.status == 401:
                    raise CupraAuthError("OLA API rejected the bearer token.")
                last_status, last_body = resp.status, body
            except (CupraAuthError, CupraAPIError):
                raise
            except Exception as exc:
                logger.debug("  %s → error: %s", url, exc)

        if vehicles_payload is None:
            if last_status == 403:
                raise CupraAPIError(
                    "OLA API returned 403 Forbidden — the token exchange service "
                    "(tokenrefreshservice.apps.emea.vwapps.io) returned 503. "
                    "This service is used by the Cupra mobile app. "
                    "Run this script on your phone via Termux — it should work from there."
                )
            raise CupraAPIError(
                f"Could not get vehicle list. Last response: {last_status} {last_body[:200]}"
            )

        # Normalise list format
        vlist: list = vehicles_payload
        if isinstance(vlist, dict):
            vlist = vlist.get("data") or vlist.get("vehicles") or list(vlist.values())[0]
        if not isinstance(vlist, list):
            vlist = [vlist]

        vin_upper = vin.upper()
        found_vins = [(v.get("vin") or v.get("id") or "").upper() for v in vlist]
        vehicle = next((v for v in vlist if (v.get("vin") or v.get("id") or "").upper() == vin_upper), None)

        if vehicle is None:
            raise CupraAPIError(
                f"VIN {vin!r} not found. VINs on account: {found_vins}"
            )
        logger.info("Found vehicle: %s", vehicle)

        # Fetch battery status
        status_urls = [
            f"{OLA_API}/v2/vehicles/{vin}/status",
            f"{OLA_API}/v1/vehicles/{vin}/status",
            f"{OLA_API}/v2/users/{user_id}/garage/vehicles/{vin}/status" if user_id else None,
        ]
        for surl in status_urls:
            if not surl:
                continue
            try:
                resp = await session.get(surl, headers=api_headers)
                body = await resp.text()
                logger.debug("status %s → %s", surl, resp.status)
                if resp.status == 200 and body.strip().startswith("{"):
                    payload = json.loads(body)
                    logger.info("Battery data: %s", body[:300])
                    return _parse_battery(payload)
            except Exception as exc:
                logger.debug("  %s error: %s", surl, exc)

        raise CupraAPIError(
            "Could not fetch battery status from any endpoint. "
            "Vehicle was found in garage — check status endpoint paths."
        )


def _parse_battery(data: dict) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "battery_level": None,
        "range_km":      None,
        "charging":      False,
        "time_to_full":  None,
    }
    vehicle = data.get("data", data)

    # Shape A — batteryStatus (Cupra Born / VW ID)
    bat = vehicle.get("batteryStatus", {})
    if bat:
        result["battery_level"] = bat.get("currentSoc_pct")
        result["range_km"]      = bat.get("cruisingRangeElectric_km")
        state = bat.get("chargingStatus", "")
        result["charging"]      = state.upper() in ("CHARGING", "CONSERVATION")
        return result

    # Shape B — fuelStatus (older endpoint)
    primary = (vehicle.get("fuelStatus", {}).get("rangeStatus", {}).get("primaryEngine", {}))
    if primary:
        result["battery_level"] = primary.get("currentSoc_pct")
        result["range_km"]      = primary.get("remainingRange_km")
        return result

    # Shape C — electric
    elec = vehicle.get("electric", {})
    if elec:
        result["battery_level"] = elec.get("soc")
        result["range_km"]      = elec.get("range")
        charge = elec.get("charging", {})
        result["charging"]      = bool(charge.get("active", False))
        return result

    logger.warning("No battery shape recognised. Top-level keys: %s", list(data.keys()))
    return result


# ── Public interface ──────────────────────────────────────────────────────────

class CupraClient:
    def __init__(self, username: str, password: str, vin: str):
        self.username = username
        self.password = password
        self.vin      = vin

    def get_battery_status(self) -> Dict[str, Any]:
        try:
            return asyncio.run(_fetch_battery(self.username, self.password, self.vin))
        except (CupraAuthError, CupraAPIError):
            raise
        except Exception as exc:
            raise CupraAPIError(f"Unexpected error: {exc}") from exc
