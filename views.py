import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from lnbits.core.models import User
from lnbits.decorators import check_user_exists
from lnbits.helpers import template_renderer
from loguru import logger

from .crud import update_extension_settings, upsert_xero_connection
from .models import CreateXeroConnection, ExtensionSettings
from .services import XERO_API_BASE, XERO_TOKEN_URL, get_settings

xerosync_generic_router = APIRouter()


def xerosync_renderer():
    return template_renderer(["xerosync/templates"])


@xerosync_generic_router.get("/", response_class=HTMLResponse)
async def index(req: Request, user: User = Depends(check_user_exists)):
    return xerosync_renderer().TemplateResponse("xerosync/index.html", {"request": req, "user": user.json()})


@xerosync_generic_router.get("/oauth/start")
async def xero_oauth_start(request: Request, user: User = Depends(check_user_exists)):
    settings = await get_settings(user.id)
    if not settings.xero_client_id or not settings.xero_client_secret:
        logger.error(f"Xero client id/secret not configured for user {user.id}")
        return HTMLResponse("Xero client id/secret not configured.", status_code=400)

    state = secrets.token_urlsafe(16)
    request.session["xero_oauth_state"] = state
    request.session["xero_oauth_user_id"] = user.id

    redirect_uri = str(request.url_for("xero_oauth_callback"))
    scopes = "openid profile email accounting.settings accounting.transactions offline_access"
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.xero_client_id,
            "redirect_uri": redirect_uri,
            "scope": scopes,
            "state": state,
        }
    )
    auth_url = f"https://login.xero.com/identity/connect/authorize?{query}"
    return RedirectResponse(auth_url)


@xerosync_generic_router.get("/oauth/callback")
async def xero_oauth_callback(request: Request, code: str | None = None, state: str | None = None):
    """
    Xero redirects here after the user clicks 'Allow access'.
    We:
      1) exchange code -> tokens
      2) fetch tenantId
      3) save connection for this LNbits user (state=user_id)
    """
    if not code or not state:
        logger.error(f"Xero OAuth callback missing code/state: code={code}, state={state}")
        return HTMLResponse("Missing code or state in Xero callback.", status_code=400)

    user_id = _consume_oauth_state(request, state)
    if not user_id:
        return HTMLResponse("Invalid or expired OAuth session.", status_code=400)
    logger.info(f"Xero OAuth callback for user {user_id}")

    # Get client id/secret from extension settings
    settings = await get_settings(user_id)
    if not settings.xero_client_id or not settings.xero_client_secret:
        logger.error(f"Xero client id/secret not configured for user {user_id}")
        return HTMLResponse("Xero client id/secret not configured.", status_code=500)

    # 1) Exchange code for tokens
    redirect_uri = str(request.url_for("xero_oauth_callback"))
    try:
        access_token, refresh_token, expires_at = await _exchange_code_for_tokens(code, redirect_uri, settings)
    except Exception as exc:
        logger.exception(f"Failed to exchange Xero code for tokens: {exc}")
        return HTMLResponse("Failed to exchange code with Xero.", status_code=400)

    # 2) Fetch tenant (organisation) id
    try:
        tenant_id = await _fetch_tenant_id(access_token)
    except Exception as exc:
        logger.exception(f"Failed to fetch Xero connections: {exc}")
        return HTMLResponse("Failed to fetch Xero organisations.", status_code=400)

    # 3) Save / update connection
    conn_data = CreateXeroConnection(
        tenant_id=tenant_id,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
    )

    await upsert_xero_connection(user_id, conn_data)

    logger.info(f"Xero connection stored for user {user_id}, tenant {tenant_id}")

    await _auto_map_tax_rates(user_id, access_token, tenant_id)

    # Simple success page
    html = """
    <html>
      <body>
        <h3>Xero connection successful ✅</h3>
        <p>You can close this tab and return to LNbits.</p>
      </body>
    </html>
    """
    return HTMLResponse(html)


def _consume_oauth_state(request: Request, state: str) -> str | None:
    stored_state = request.session.get("xero_oauth_state")
    user_id = request.session.get("xero_oauth_user_id")
    if not stored_state or not user_id or stored_state != state:
        logger.error("Xero OAuth callback state mismatch or missing session.")
        return None
    request.session.pop("xero_oauth_state", None)
    request.session.pop("xero_oauth_user_id", None)
    return user_id


async def _exchange_code_for_tokens(
    code: str, redirect_uri: str, settings: ExtensionSettings
) -> tuple[str, str, datetime]:
    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": settings.xero_client_id,
        "client_secret": settings.xero_client_secret,
    }
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(XERO_TOKEN_URL, data=token_data, timeout=10)
    token_resp.raise_for_status()
    body = token_resp.json()
    access_token = body["access_token"]
    refresh_token = body["refresh_token"]
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=body["expires_in"])
    return access_token, refresh_token, expires_at


async def _fetch_tenant_id(access_token: str) -> str:
    async with httpx.AsyncClient() as client:
        conn_resp = await client.get(
            "https://api.xero.com/connections",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
    conn_resp.raise_for_status()
    connections = conn_resp.json()
    if not connections:
        raise ValueError("No Xero organisations found.")
    return connections[0]["tenantId"]


def _collect_tax_candidates(taxrates: list[dict]) -> tuple[list, list, list, list]:
    rev_rates = []
    zero_rev_rates = []
    avalara_rates = []
    exempt_candidates = []
    for tr in taxrates:
        if tr.get("Status") == "DELETED":
            continue
        tax_type = tr.get("TaxType")
        name = (tr.get("Name") or "").lower()
        rate = tr.get("EffectiveRate") or tr.get("DisplayTaxRate")
        can_rev = tr.get("CanApplyToRevenue", False)
        try:
            rate_val = float(rate) if rate is not None else None
        except (TypeError, ValueError):
            rate_val = None
        is_avalara = "avalara" in name or (tax_type and "AVALARA" in tax_type.upper())
        if can_rev and rate_val is not None:
            rev_rates.append((rate_val, tax_type, name, is_avalara))
            if rate_val == 0:
                zero_rev_rates.append((rate_val, tax_type, name, is_avalara))
        if is_avalara and can_rev:
            avalara_rates.append((rate_val, tax_type, name, is_avalara))
        if "exempt" in name or "out of scope" in name:
            exempt_candidates.append((rate_val, tax_type, name, is_avalara))
    return rev_rates, zero_rev_rates, avalara_rates, exempt_candidates


def _select_standard(rev_rates: list, avalara_rates: list) -> str | None:
    non_avalara_positive = [r for r in rev_rates if r[0] > 0 and not r[3]]
    if non_avalara_positive:
        non_avalara_positive.sort(key=lambda x: x[0], reverse=True)
        return non_avalara_positive[0][1]
    if avalara_rates:
        avalara_rates.sort(key=lambda x: (x[0] is None, x[0] or 0), reverse=True)
        return avalara_rates[0][1]
    if rev_rates:
        rev_rates.sort(key=lambda x: (x[0] is None, x[0] or 0), reverse=True)
        return rev_rates[0][1]
    return None


def _select_zero(zero_rev_rates: list) -> str | None:
    zero_candidates = [
        r for r in zero_rev_rates if not r[3] and ("zero" in r[2] or "0%" in r[2] or "no tax" in r[2] or "none" in r[2])
    ]
    if zero_candidates:
        return zero_candidates[0][1]
    return None


def _select_exempt(exempt_candidates: list) -> str | None:
    if not exempt_candidates:
        return None
    non_avalara_exempt = [r for r in exempt_candidates if not r[3]]
    if non_avalara_exempt:
        return non_avalara_exempt[0][1]
    return exempt_candidates[0][1]


async def _auto_map_tax_rates(user_id: str, access_token: str, tenant_id: str) -> None:
    try:
        async with httpx.AsyncClient() as client:
            tax_resp = await client.get(
                f"{XERO_API_BASE}/TaxRates",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "xero-tenant-id": tenant_id,
                    "Accept": "application/json",
                },
                timeout=10,
            )
        tax_resp.raise_for_status()
        tax_body = tax_resp.json()
        taxrates = tax_body.get("TaxRates", [])
        rev_rates, zero_rev_rates, avalara_rates, exempt_candidates = _collect_tax_candidates(taxrates)
        standard = _select_standard(rev_rates, avalara_rates)
        zero = _select_zero(zero_rev_rates)
        exempt = _select_exempt(exempt_candidates)
        settings = await get_settings(user_id)
        if standard and not getattr(settings, "xero_tax_standard", None):
            settings.xero_tax_standard = standard
        if zero and not getattr(settings, "xero_tax_zero", None):
            settings.xero_tax_zero = zero
        if exempt and not getattr(settings, "xero_tax_exempt", None):
            settings.xero_tax_exempt = exempt
        await update_extension_settings(user_id, settings)
        logger.info(
            f"Auto-mapped Xero tax types for user {user_id}: " f"standard={standard}, zero={zero}, exempt={exempt}"
        )
    except Exception as exc:
        logger.warning(f"Failed to auto-map Xero tax types: {exc}")
