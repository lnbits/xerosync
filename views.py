from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from lnbits.core.models import User
from lnbits.decorators import check_user_exists
from lnbits.helpers import template_renderer
from loguru import logger
import httpx
from datetime import datetime, timedelta, timezone
from .crud import upsert_xero_connection, update_extension_settings
from .models import CreateXeroConnection
from .services import get_settings, XERO_TOKEN_URL, XERO_API_BASE
xero_sync_generic_router = APIRouter()


def xero_sync_renderer():
    return template_renderer(["xero_sync/templates"])


@xero_sync_generic_router.get("/", response_class=HTMLResponse)
async def index(req: Request, user: User = Depends(check_user_exists)):
    return xero_sync_renderer().TemplateResponse("xero_sync/index.html", {"request": req, "user": user.json()})


@xero_sync_generic_router.get("/oauth/callback")
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

    user_id = state
    logger.info(f"Xero OAuth callback for user {user_id}")

    # Get client id/secret from extension settings
    settings = await get_settings(user_id)
    if not settings.xero_client_id or not settings.xero_client_secret:
        logger.error("Xero client id/secret not configured for user {user_id}")
        return HTMLResponse("Xero client id/secret not configured.", status_code=500)

    # 1) Exchange code for tokens
    redirect_uri = str(request.url_for("xero_oauth_callback"))
    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": settings.xero_client_id,
        "client_secret": settings.xero_client_secret,
    }

    try:
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(XERO_TOKEN_URL, data=token_data, timeout=10)
        token_resp.raise_for_status()
    except Exception as e:
        logger.exception(f"Failed to exchange Xero code for tokens: {e}")
        return HTMLResponse("Failed to exchange code with Xero.", status_code=400)

    body = token_resp.json()
    access_token = body["access_token"]
    refresh_token = body["refresh_token"]
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=body["expires_in"])

    # 2) Fetch tenant (organisation) id
    try:
        async with httpx.AsyncClient() as client:
            conn_resp = await client.get(
                "https://api.xero.com/connections",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
        conn_resp.raise_for_status()
    except Exception as e:
        logger.exception(f"Failed to fetch Xero connections: {e}")
        return HTMLResponse("Failed to fetch Xero organisations.", status_code=400)

    connections = conn_resp.json()
    if not connections:
        logger.error("Xero returned no organisations for user {user_id}")
        return HTMLResponse("No Xero organisations found for this account.", status_code=400)

    tenant_id = connections[0]["tenantId"]

    # 3) Save / update connection
    conn_data = CreateXeroConnection(
        tenant_id=tenant_id,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
    )

    await upsert_xero_connection(user_id, conn_data)

    logger.info(f"Xero connection stored for user {user_id}, tenant {tenant_id}")

    # 4) Auto-fetch TaxRates and prefill standard/zero/exempt mapping
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

        # --- Heuristic auto-mapping of standard / zero / exempt ---
        standard = None
        zero = None
        exempt = None

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

            # Collect buckets
            if can_rev and rate_val is not None:
                rev_rates.append((rate_val, tax_type, name, is_avalara))
                if rate_val == 0:
                    zero_rev_rates.append((rate_val, tax_type, name, is_avalara))

            if is_avalara and can_rev:
                avalara_rates.append((rate_val, tax_type, name, is_avalara))

            if "exempt" in name or "out of scope" in name:
                exempt_candidates.append((rate_val, tax_type, name, is_avalara))

        # 1) STANDARD: prefer non-Avalara revenue rate > 0; else Avalara; else highest revenue rate
        non_avalara_positive = [
            r for r in rev_rates if r[0] > 0 and not r[3]
        ]
        if non_avalara_positive:
            # pick highest rate non-avalara as "standard"
            non_avalara_positive.sort(key=lambda x: x[0], reverse=True)
            standard = non_avalara_positive[0][1]
        elif avalara_rates:
            # Avalara-only org: treat Avalara as "standard"
            avalara_rates.sort(key=lambda x: (x[0] is None, x[0] or 0), reverse=True)
            standard = avalara_rates[0][1]
        elif rev_rates:
            # fallback: any revenue rate
            rev_rates.sort(key=lambda x: (x[0] is None, x[0] or 0), reverse=True)
            standard = rev_rates[0][1]

        # 2) ZERO: revenue rate with 0% AND name hinting zero/no tax, and not Avalara
        zero_candidates = [
            r for r in zero_rev_rates
            if not r[3] and (
                "zero" in r[2]
                or "0%" in r[2]
                or "no tax" in r[2]
                or "none" in r[2]
            )
        ]
        if zero_candidates:
            zero = zero_candidates[0][1]

        # 3) EXEMPT: first exempt-ish name, prefer non-Avalara
        if exempt_candidates:
            non_avalara_exempt = [r for r in exempt_candidates if not r[3]]
            if non_avalara_exempt:
                exempt = non_avalara_exempt[0][1]
            else:
                exempt = exempt_candidates[0][1]

        # --- Persist only non-None values, and don't overwrite manual config ---
        settings = await get_settings(user_id)
        if standard and not getattr(settings, "xero_tax_standard", None):
            settings.xero_tax_standard = standard
        if zero and not getattr(settings, "xero_tax_zero", None):
            settings.xero_tax_zero = zero
        if exempt and not getattr(settings, "xero_tax_exempt", None):
            settings.xero_tax_exempt = exempt

        await update_extension_settings(user_id, settings)

        logger.info(
            f"Auto-mapped Xero tax types for user {user_id}: "
            f"standard={standard}, zero={zero}, exempt={exempt}"
        )
    except Exception as e:
        logger.warning(f"Failed to auto-map Xero tax types: {e}")

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
