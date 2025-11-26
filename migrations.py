empty_dict: dict[str, str] = {}


async def m001_extension_settings(db):
    """
    Initial settings table.
    """
    prefix = "" if getattr(db, "type", "").upper() == "SQLITE" else "xero_sync."

    await db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {prefix}extension_settings (
            id TEXT NOT NULL,
            xero_client_id TEXT,
            xero_client_secret TEXT,
            xero_tax_standard TEXT,
            xero_tax_zero TEXT,
            xero_tax_exempt TEXT,
            updated_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now}
        );
    """
    )


async def m002_wallets(db):
    """
    Initial wallets table.
    """
    prefix = "" if getattr(db, "type", "").upper() == "SQLITE" else "xero_sync."
    tbl = f"{prefix}wallets"

    await db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {tbl} (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            wallet TEXT NOT NULL,
            pull_payments BOOLEAN NOT NULL,
            push_payments BOOLEAN NOT NULL,
            reconcile_name TEXT,
            reconcile_mode TEXT,
            xero_bank_account_id TEXT,
            tax_rate INTEGER,
            fee_handling BOOLEAN,
            last_synced TIMESTAMP,
            status TEXT,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now},
            updated_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now}
        );
    """
    )

async def m003_wallet_indexes(db):
    """
    Add indexes to speed up lookups by wallet id when a payment arrives.
    """
    prefix = "" if getattr(db, "type", "").upper() == "SQLITE" else "xero_sync."
    tbl = f"{prefix}wallets"
    await db.execute(
        f"""
        CREATE INDEX IF NOT EXISTS xero_sync_wallets_wallet_push_idx
        ON {tbl} (wallet, push_payments);
        """
    )

async def m004_xero_connections(db):
    """
    Table to store per-user Xero OAuth connection (tokens + tenant id).
    """
    prefix = "" if getattr(db, "type", "").upper() == "SQLITE" else "xero_sync."
    tbl = f"{prefix}connections"

    # Create table
    await db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {tbl} (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            access_token TEXT NOT NULL,
            refresh_token TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now},
            updated_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now}
        );
        """
    )

    # Helpful index for fast lookups by user
    await db.execute(
        f"""
        CREATE INDEX IF NOT EXISTS xero_sync_connections_user_idx
        ON {tbl} (user_id);
        """
    )


async def m005_wallet_tax_rate_text(db):
    """
    Make wallet tax_rate text-based to store descriptive codes (standard/zero/exempt).
    """
    prefix = "" if getattr(db, "type", "").upper() == "SQLITE" else "xero_sync."
    tbl = f"{prefix}wallets"
    is_pg = getattr(db, "type", "").upper() == "POSTGRES"

    if is_pg:
        await db.execute(
            f"""
            ALTER TABLE {tbl}
            ALTER COLUMN tax_rate TYPE TEXT
            USING tax_rate::TEXT;
            """
        )
    # SQLite allows storing text in an INTEGER affinity column, so no change needed.


async def m006_synced_payments(db):
    """
    Track which payments have been pushed to Xero to avoid duplicates.
    """
    prefix = "" if getattr(db, "type", "").upper() == "SQLITE" else "xero_sync."
    tbl = f"{prefix}synced_payments"

    await db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {tbl} (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            wallet_id TEXT NOT NULL,
            payment_hash TEXT NOT NULL UNIQUE,
            xero_bank_transaction_id TEXT,
            currency TEXT,
            amount REAL,
            created_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now}
        );
        """
    )

    await db.execute(
        f"""
        CREATE INDEX IF NOT EXISTS xero_sync_synced_payments_wallet_idx
        ON {tbl} (wallet_id);
        """
    )
