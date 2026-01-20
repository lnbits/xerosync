import httpx
from datetime import datetime, timedelta, timezone
from lnbits.core.crud import get_payments
from lnbits.core.models import Payment
from loguru import logger
from .crud import (
    create_extension_settings,
    get_extension_settings,
    create_synced_payment,
    update_synced_payment,
    delete_synced_payment,
    get_synced_payment,
    get_synced_payment_hashes,
    update_extension_settings,
    update_xero_connection,
    get_xero_connection,
    update_wallets,
)
from .models import ExtensionSettings, Wallets

XERO_TOKEN_URL = "https://identity.xero.com/connect/token"
XERO_API_BASE = "https://api.xero.com/api.xro/2.0"
EMPTY_ACCOUNT_ID = "00000000-0000-0000-0000-000000000000"

# -- Xero API helpers ---------------------------------------------------------
async def fetch_xero_accounts(access_token: str, tenant_id: str) -> list[dict]:
    """
    Fetch Xero Accounts (chart of accounts).
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{XERO_API_BASE}/Accounts",
            headers={
                "Authorization": f"Bearer {access_token}",
                "xero-tenant-id": tenant_id,
                "Accept": "application/json",
            },
            timeout=10,
        )
    resp.raise_for_status()
    body = resp.json()
    return body.get("Accounts", [])


async def fetch_xero_bank_accounts(access_token: str, tenant_id: str) -> list[dict]:
    """
    Fetch Xero Bank accounts (for deposit target selection).
    """
    accounts = await fetch_xero_accounts(access_token, tenant_id)
    return [acc for acc in accounts if acc.get("Type") == "BANK"]

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


def _build_bank_transaction_payload(
    payment: Payment, wallet_cfg: Wallets, settings: ExtensionSettings
) -> tuple[dict | None, float | None, str | None, str | None]:
    """
    Prepare the Xero BankTransaction payload for a payment.
    Returns (payload, amount_major, currency, skip_reason).
    """
    if payment.amount <= 0:
        return None, None, None, "payment is not incoming"

    extra = payment.extra or {}
    fiat_currency = extra.get("wallet_fiat_currency")
    fiat_amount = extra.get("wallet_fiat_amount")

    if not fiat_currency or fiat_amount is None:
        return None, None, None, "missing fiat currency/amount"

    if (
        not wallet_cfg.xero_bank_account_id
        or wallet_cfg.xero_bank_account_id == EMPTY_ACCOUNT_ID
    ):
        return None, None, None, "wallet missing xero_bank_account_id"

    raw_amount = float(fiat_amount)
    amount_major = round(raw_amount, 2)
    if amount_major <= 0:
        return None, None, None, "fiat amount too small after rounding"

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
    if wallet_cfg.auto_reconcile:
        bank_tx["IsReconciled"] = True

    return bank_tx, amount_major, fiat_currency, None


def _as_datetime(val) -> datetime:
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromtimestamp(val, tz=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _is_unique_violation(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "unique" in msg or "duplicate" in msg


async def push_payment_to_xero(
    payment: Payment,
    conn,
    wallet_cfg: Wallets,
    settings: ExtensionSettings,
    access_token: str,
    tenant_id: str,
    known_synced_hashes: set[str] | None = None,
) -> dict:
    """
    Push a single payment to Xero, guarding against duplicates.
    Returns a dict with status: ok | skip | error and optional message/id.
    """
    if known_synced_hashes is not None:
        if payment.payment_hash in known_synced_hashes:
            return {"status": "skip", "reason": "already synced"}
    else:
        existing = await get_synced_payment(payment.payment_hash)
        if existing:
            return {"status": "skip", "reason": "already synced"}

    bank_tx, amount_major, fiat_currency, skip_reason = _build_bank_transaction_payload(
        payment, wallet_cfg, settings
    )
    if skip_reason:
        logger.debug(
            f"Xero Sync: skipping payment {payment.payment_hash} ({skip_reason})"
        )
        return {"status": "skip", "reason": skip_reason}

    try:
        await create_synced_payment(
            wallet_cfg.user_id,
            wallet_cfg.wallet,
            payment.payment_hash,
            None,
            fiat_currency.upper() if fiat_currency else None,
            amount_major,
        )
    except Exception as exc:
        if _is_unique_violation(exc):
            logger.debug(
                f"Xero Sync: payment {payment.payment_hash} already reserved, skipping"
            )
            return {"status": "skip", "reason": "already synced"}
        raise

    if known_synced_hashes is not None:
        known_synced_hashes.add(payment.payment_hash)

    payload = {"BankTransactions": [bank_tx]}

    try:
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
    except Exception:
        await delete_synced_payment(payment.payment_hash)
        raise

    if resp.status_code >= 300:
        await delete_synced_payment(payment.payment_hash)
        logger.error(
            f"Xero Sync: failed to create bank transaction for wallet "
            f"{payment.wallet_id} ({resp.status_code}): {resp.text}"
        )
        return {"status": "error", "reason": resp.text, "code": resp.status_code}

    bank_tx_id = None
    try:
        body = resp.json()
        bank_tx_id = (
            body.get("BankTransactions", [{}])[0].get("BankTransactionID")
            if isinstance(body, dict)
            else None
        )
    except Exception:
        bank_tx_id = None

    await update_synced_payment(
        payment.payment_hash,
        bank_tx_id,
        fiat_currency.upper() if fiat_currency else None,
        amount_major,
    )

    logger.debug(
        f"Xero Sync: created Xero BankTransaction for payment {payment.payment_hash} "
        f"{amount_major} {fiat_currency.upper() if fiat_currency else ''}"
    )
    return {"status": "ok", "bank_transaction_id": bank_tx_id}


async def payment_received_for_client_data(payment: Payment, conn, wallet_cfg) -> bool:
    # Load Xero app settings (client id/secret) for this user
    settings = await get_settings(wallet_cfg.user_id)
    access_token, tenant_id = await ensure_xero_access_token(conn, settings)

    result = await push_payment_to_xero(
        payment,
        conn,
        wallet_cfg,
        settings,
        access_token,
        tenant_id,
    )

    if result["status"] == "ok":
        wallet_cfg.last_synced = _as_datetime(getattr(payment, "time", None))
        wallet_cfg.status = f"Auto-synced payment {payment.payment_hash}"
        await update_wallets(wallet_cfg)
        return True

    if result["status"] == "skip":
        return True

    return False


async def sync_wallet_payments(wallet_cfg: Wallets) -> dict:
    """
    Push all current successful incoming payments for a wallet to Xero.
    """
    conn = await get_xero_connection(wallet_cfg.user_id)
    if not conn:
        raise RuntimeError("Xero Sync: no Xero connection for this user.")

    settings = await get_settings(wallet_cfg.user_id)
    access_token, tenant_id = await ensure_xero_access_token(conn, settings)

    payments = await get_payments(
        wallet_id=wallet_cfg.wallet, incoming=True, complete=True
    )
    payments = sorted(payments, key=lambda p: _as_datetime(p.time))

    synced_hashes = await get_synced_payment_hashes(wallet_cfg.wallet)
    summary = {"pushed": 0, "skipped": 0, "failed": 0, "errors": []}

    for pay in payments:
        try:
            result = await push_payment_to_xero(
                pay,
                conn,
                wallet_cfg,
                settings,
                access_token,
                tenant_id,
                known_synced_hashes=synced_hashes,
            )
        except Exception as exc:  # keep iterating on errors
            logger.error(f"Xero Sync: failed to push payment {pay.payment_hash}: {exc}")
            summary["failed"] += 1
            summary["errors"].append(str(exc))
            continue

        if result["status"] == "ok":
            summary["pushed"] += 1
        elif result["status"] == "skip":
            summary["skipped"] += 1
        else:
            summary["failed"] += 1
            summary["errors"].append(result.get("reason") or "unknown error")

    now = datetime.now(timezone.utc)
    wallet_cfg.last_synced = now
    wallet_cfg.status = (
        f"Synced {summary['pushed']} (skipped {summary['skipped']}, "
        f"errors {summary['failed']}) at {now.isoformat()}"
    )
    await update_wallets(wallet_cfg)
    return summary


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
