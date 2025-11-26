from lnbits.db import Database, Filters, Page
from lnbits.helpers import urlsafe_short_hash
from datetime import datetime, timezone

from .models import (
    CreateWallets,
    ExtensionSettings,  #
    UserExtensionSettings,  #
    Wallets,
    WalletsFilters,
    XeroConnection,
    CreateXeroConnection,
    SyncedPayment,
)

db = Database("ext_xero_sync")


########################### Wallets ############################
async def create_wallets(user_id: str, data: CreateWallets) -> Wallets:
    wallets = Wallets(**data.dict(), id=urlsafe_short_hash(), user_id=user_id)
    await db.insert("xero_sync.wallets", wallets)
    return wallets


async def get_wallets(
    user_id: str,
    wallets_id: str,
) -> Wallets | None:
    return await db.fetchone(
        """
            SELECT * FROM xero_sync.wallets
            WHERE id = :id AND user_id = :user_id
        """,
        {"id": wallets_id, "user_id": user_id},
        Wallets,
    )


async def get_wallets_by_id(
    wallets_id: str,
) -> Wallets | None:
    return await db.fetchone(
        """
            SELECT * FROM xero_sync.wallets
            WHERE id = :id
        """,
        {"id": wallets_id},
        Wallets,
    )

async def get_wallet_by_wallet_id(wallet_id: str) -> Wallets | None:
    return await db.fetchone(
        """
        SELECT * FROM xero_sync.wallets
        WHERE wallet = :wallet AND push_payments = TRUE
        """,
        {"wallet": wallet_id},
        Wallets,
    )

async def get_wallets_ids_by_user(
    user_id: str,
) -> list[str]:
    rows: list[dict] = await db.fetchall(
        """
            SELECT DISTINCT id FROM xero_sync.wallets
            WHERE user_id = :user_id
        """,
        {"user_id": user_id},
    )

    return [row["id"] for row in rows]


async def get_wallets_paginated(
    user_id: str | None = None,
    filters: Filters[WalletsFilters] | None = None,
) -> Page[Wallets]:
    where = []
    values = {}
    if user_id:
        where.append("user_id = :user_id")
        values["user_id"] = user_id

    return await db.fetch_page(
        "SELECT * FROM xero_sync.wallets",
        where=where,
        values=values,
        filters=filters,
        model=Wallets,
        table_name="xero_sync.wallets",
    )


async def update_wallets(data: Wallets) -> Wallets:
    await db.update("xero_sync.wallets", data)
    return data


async def delete_wallets(user_id: str, wallets_id: str) -> None:
    await db.execute(
        """
            DELETE FROM xero_sync.wallets
            WHERE id = :id AND user_id = :user_id
        """,
        {"id": wallets_id, "user_id": user_id},
    )


############################ Settings #############################
async def create_extension_settings(user_id: str, data: ExtensionSettings) -> ExtensionSettings:
    settings = UserExtensionSettings(**data.dict(), id=user_id)
    await db.insert("xero_sync.extension_settings", settings)
    return settings


async def get_extension_settings(
    user_id: str,
) -> ExtensionSettings | None:
    return await db.fetchone(
        """
            SELECT * FROM xero_sync.extension_settings
            WHERE id = :user_id
        """,
        {"user_id": user_id},
        ExtensionSettings,
    )


async def update_extension_settings(user_id: str, data: ExtensionSettings) -> ExtensionSettings:
    settings = UserExtensionSettings(**data.dict(), id=user_id)
    await db.update("xero_sync.extension_settings", settings)
    return settings


######################## Xero Connections ########################
async def create_xero_connection(
    user_id: str, data: CreateXeroConnection
) -> XeroConnection:
    now = datetime.now(timezone.utc)
    conn = XeroConnection(
        **data.dict(),
        id=urlsafe_short_hash(),
        user_id=user_id,
        created_at=now,
        updated_at=now,
    )
    await db.insert("xero_sync.connections", conn)
    return conn


async def update_xero_connection(conn: XeroConnection) -> XeroConnection:
    conn.updated_at = datetime.now(timezone.utc)
    await db.update("xero_sync.connections", conn)
    return conn


async def get_xero_connection(user_id: str) -> XeroConnection | None:
    """
    Fetch the latest Xero connection for this user, if any.
    """
    return await db.fetchone(
        f"""
        SELECT *
        FROM xero_sync.connections
        WHERE user_id = :user_id
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        {"user_id": user_id},
        XeroConnection,
    )

async def upsert_xero_connection(
    user_id: str,
    data: CreateXeroConnection,
) -> XeroConnection:
    """
    Insert or update the Xero connection for this user.
    """
    existing = await get_xero_connection(user_id)

    if existing:
        updated = existing.copy(update=data.dict())
        return await update_xero_connection(updated)

    return await create_xero_connection(user_id, data)


######################## Synced Payments ########################
async def create_synced_payment(
    user_id: str,
    wallet_id: str,
    payment_hash: str,
    xero_bank_transaction_id: str | None,
    currency: str | None,
    amount: float | None,
) -> SyncedPayment:
    rec = SyncedPayment(
        id=urlsafe_short_hash(),
        user_id=user_id,
        wallet_id=wallet_id,
        payment_hash=payment_hash,
        xero_bank_transaction_id=xero_bank_transaction_id,
        currency=currency,
        amount=amount,
    )
    await db.insert("xero_sync.synced_payments", rec)
    return rec


async def get_synced_payment(payment_hash: str) -> SyncedPayment | None:
    return await db.fetchone(
        """
        SELECT * FROM xero_sync.synced_payments
        WHERE payment_hash = :payment_hash
        """,
        {"payment_hash": payment_hash},
        SyncedPayment,
    )


async def get_synced_payment_hashes(wallet_id: str) -> set[str]:
    rows = await db.fetchall(
        """
        SELECT payment_hash FROM xero_sync.synced_payments
        WHERE wallet_id = :wallet_id
        """,
        {"wallet_id": wallet_id},
    )
    return {row["payment_hash"] for row in rows}
