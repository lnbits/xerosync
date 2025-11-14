from lnbits.core.models import Payment
from loguru import logger
import httpx
from datetime import datetime, timedelta, timezone
from .crud import (
    create_extension_settings,
    get_extension_settings,
    update_extension_settings,
    update_xero_connection,
)
from .models import ExtensionSettings

XERO_TOKEN_URL = "https://identity.xero.com/connect/token"
XERO_API_BASE = "https://api.xero.com/api.xro/2.0"

async def fetch_xero_tax_rates_raw(access_token: str, tenant_id: str) -> list[dict]:
    """
    Low-level helper to fetch TaxRates from Xero.
    Returns the raw Xero dicts.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{XERO_API_BASE}/TaxRates",
            headers={
                "Authorization": f"Bearer {access_token}",
                "xero-tenant-id": tenant_id,
                "Accept": "application/json",
            },
            timeout=10,
        )
    resp.raise_for_status()
    body = resp.json()
    return body.get("TaxRates", [])

async def ensure_xero_access_token(conn, settings: ExtensionSettings) -> tuple[str, str]:
    """
    Make sure we have a valid access token.
    Returns (access_token, tenant_id).
    """

    # We must have client id/secret configured in settings
    if not settings.xero_client_id or not settings.xero_client_secret:
        raise RuntimeError("Xero Sync: client id/secret not configured in settings")

    # If token is still good for > 2 minutes, use it
    now = datetime.now(timezone.utc)
    if conn.expires_at and conn.expires_at > now + timedelta(minutes=2):
        return conn.access_token, conn.tenant_id

    # Refresh
    data = {
        "grant_type": "refresh_token",
        "refresh_token": conn.refresh_token,
        "client_id": settings.xero_client_id,
        "client_secret": settings.xero_client_secret,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(XERO_TOKEN_URL, data=data, timeout=10)

    resp.raise_for_status()
    body = resp.json()

    conn.access_token = body["access_token"]
    conn.refresh_token = body["refresh_token"]
    conn.expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=body["expires_in"]
    )

    await update_xero_connection(conn)

    return conn.access_token, conn.tenant_id


async def payment_received_for_client_data(payment: Payment, conn, wallet_cfg) -> bool:
    # Load Xero app settings (client id/secret) for this user
    settings = await get_settings(wallet_cfg.user_id)

    access_token, tenant_id = await ensure_xero_access_token(conn, settings)

    # --- Only push if fiat data exists ---
    extra = payment.extra or {}  # <-- avoid NoneType.get crash
    fiat_currency = extra.get("wallet_fiat_currency")
    fiat_amount = extra.get("wallet_fiat_amount")

    if not fiat_currency or fiat_amount is None:
        logger.debug(
            f"Xero Sync: skipping payment {payment.payment_hash} "
            f"because fiat data is missing (extra={extra})"
        )
        return True
    if not wallet_cfg.xero_bank_account_id or wallet_cfg.xero_bank_account_id == "00000000-0000-0000-0000-000000000000":
        logger.debug(
            f"Xero Sync: skipping payment {payment.payment_hash} "
            f"because wallet has no valid xero_bank_account_id"
        )
        return True
    # Xero expects *major units* (not sats)
    # LNbits already gives you the ready-to-post fiat amount here.
    raw_amount = float(fiat_amount)
    amount_major = round(raw_amount, 2)

    if amount_major <= 0:
        logger.debug(
            f"Xero Sync: skipping payment {payment.payment_hash} "
            f"because fiat amount too small after rounding ({raw_amount} -> {amount_major})"
        )
        return True

    description = payment.memo or f"LNbits payment {payment.payment_hash}"
    account_code = wallet_cfg.reconcile_mode or "200"  # Sales by default
    tax_type: str | None = None
    tr = getattr(wallet_cfg, "tax_rate", None)

    if tr == "standard":
        tax_type = settings.xero_tax_standard
    elif tr == "zero":
        tax_type = settings.xero_tax_zero
    elif tr == "exempt":
        tax_type = settings.xero_tax_exempt

    bank_tx = {
        "Type": "RECEIVE",
        "Contact": {
            "Name": wallet_cfg.reconcile_name or "LNbits Customer",
        },
        "BankAccount": {
            "AccountID": wallet_cfg.xero_bank_account_id,
        },
        "LineItems": [
            {
                "Description": description,
                "Quantity": 1,
                "UnitAmount": amount_major,
                "AccountCode": account_code,
                "TaxType": tax_type,
            }
        ],
        "Reference": description,
        "CurrencyCode": fiat_currency.upper(),
        "Date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
    }

    payload = {"BankTransactions": [bank_tx]}

    # 2) POST to Xero
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{XERO_API_BASE}/BankTransactions",
            json=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "xero-tenant-id": tenant_id,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=10,
        )

    if resp.status_code >= 300:
        logger.error(
            f"Xero Sync: failed to create bank transaction for wallet "
            f"{payment.wallet_id} ({resp.status_code}): {resp.text}"
        )
        return False

    logger.debug(
        f"Xero Sync: created Xero BankTransaction for payment {payment.payment_hash} "
        f"{amount_major} {fiat_currency.upper()}"
    )
    return True


async def get_settings(user_id: str) -> ExtensionSettings:
    settings = await get_extension_settings(user_id)
    if not settings:
        settings = await create_extension_settings(user_id, ExtensionSettings())
    return settings


async def update_settings(user_id: str, data: ExtensionSettings) -> ExtensionSettings:
    settings = await get_extension_settings(user_id)
    if not settings:
        settings = await create_extension_settings(user_id, data)
    else:
        settings = await update_extension_settings(user_id, data)

    return settings
