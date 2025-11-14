from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from lnbits.core.models import User
from lnbits.decorators import check_user_exists
from lnbits.helpers import template_renderer
from loguru import logger
import httpx
from datetime import datetime, timedelta, timezone
from .crud import upsert_xero_connection
from .models import CreateXeroConnection
from .services import get_settings, XERO_TOKEN_URL
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
    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "http://localhost:5000/xero_sync/oauth/callback",
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
