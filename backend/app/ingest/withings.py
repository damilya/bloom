"""Withings Public API (OAuth2) — pulls smart-scale measurements from the Withings cloud.

Flow: the scale syncs to the Withings cloud → we never talk to the scale itself.
  1. GET /withings/connect  → redirect to Withings consent page
  2. Withings redirects to WITHINGS_REDIRECT_URI (/withings/callback?code=...)
  3. exchange code → access + refresh token (access token lives ~3h) → stored in SQLite
  4. POST /withings/sync → getmeas, refreshing the token when needed
Docs: https://developer.withings.com/api-reference/
"""
import secrets
import time
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.config import get_settings
from app.data import db

AUTH_URL = "https://account.withings.com/oauth2_user/authorize2"
TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"
MEASURE_URL = "https://wbsapi.withings.net/measure"

# Withings measure type → (our metric, unit)
MEAS_TYPES = {
    1: ("weight_kg", "kg"),
    6: ("body_fat_pct", "%"),
    8: ("fat_mass_kg", "kg"),
    76: ("muscle_mass_kg", "kg"),
    77: ("hydration_kg", "kg"),
    88: ("bone_mass_kg", "kg"),
    11: ("resting_hr", "bpm"),
}

_pending_states: set[str] = set()


class WithingsError(RuntimeError):
    pass


def authorize_url() -> str:
    s = get_settings()
    if not s.has_withings:
        raise WithingsError("WITHINGS_CLIENT_ID / WITHINGS_CLIENT_SECRET are not set in .env")
    state = secrets.token_urlsafe(16)
    _pending_states.add(state)
    return AUTH_URL + "?" + urlencode({
        "response_type": "code", "client_id": s.withings_client_id, "scope": "user.metrics",
        "redirect_uri": s.withings_redirect_uri, "state": state,
    })


def _save_tokens(body: dict) -> None:
    with db.connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO oauth_tokens(provider, access_token, refresh_token, expires_at, user_id) "
            "VALUES('withings', ?, ?, ?, ?)",
            (body["access_token"], body["refresh_token"], time.time() + body["expires_in"] - 60, str(body["userid"])),
        )


def _token_request(data: dict) -> dict:
    s = get_settings()
    resp = httpx.post(TOKEN_URL, data={"action": "requesttoken", "client_id": s.withings_client_id,
                                       "client_secret": s.withings_client_secret, **data}, timeout=20)
    payload = resp.json()
    if payload.get("status") != 0:
        raise WithingsError(f"Withings token error: {payload}")
    return payload["body"]


def exchange_code(code: str, state: str | None) -> dict:
    if state is not None and _pending_states and state not in _pending_states:
        raise WithingsError("Invalid OAuth state")
    _pending_states.discard(state or "")
    body = _token_request({"grant_type": "authorization_code", "code": code,
                           "redirect_uri": get_settings().withings_redirect_uri})
    _save_tokens(body)
    return {"connected": True, "user_id": body["userid"]}


def _access_token() -> str:
    tok = db.rows("SELECT * FROM oauth_tokens WHERE provider='withings'")
    if not tok:
        raise WithingsError("Withings is not connected yet — open /withings/connect first")
    tok = tok[0]
    if tok["expires_at"] < time.time():
        body = _token_request({"grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})
        _save_tokens(body)
        return body["access_token"]
    return tok["access_token"]


def status() -> dict:
    tok = db.rows("SELECT user_id, expires_at FROM oauth_tokens WHERE provider='withings'")
    last = db.rows("SELECT MAX(ts) ts FROM measurements WHERE source='withings'")
    return {"configured": get_settings().has_withings, "connected": bool(tok),
            "last_measurement": last[0]["ts"] if last else None}


def sync(days: int = 365) -> dict:
    token = _access_token()
    start = int((datetime.now() - timedelta(days=days)).timestamp())
    records: list[dict] = []
    offset = None
    while True:
        data = {"action": "getmeas", "meastypes": ",".join(map(str, MEAS_TYPES)), "category": 1, "startdate": start}
        if offset:
            data["offset"] = offset
        resp = httpx.post(MEASURE_URL, data=data, headers={"Authorization": f"Bearer {token}"}, timeout=30)
        payload = resp.json()
        if payload.get("status") != 0:
            raise WithingsError(f"Withings getmeas error: {payload}")
        body = payload["body"]
        for grp in body.get("measuregrps", []):
            # home timezone, not the machine's (the laptop may be travelling)
            ts = datetime.fromtimestamp(grp["date"], tz=get_settings().tz).strftime("%Y-%m-%dT%H:%M:%S")
            for m in grp["measures"]:
                if m["type"] in MEAS_TYPES:
                    metric, unit = MEAS_TYPES[m["type"]]
                    records.append({"ts": ts, "source": "withings", "metric": metric,
                                    "value": round(m["value"] * 10 ** m["unit"], 2), "unit": unit})
        if not body.get("more"):
            break
        offset = body.get("offset")
    n = db.upsert_measurements(records) if records else 0
    from app.ingest.dedupe import dedupe_all

    return {"measurements": n, "deduplicated": dedupe_all()}
