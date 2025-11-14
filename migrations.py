empty_dict: dict[str, str] = {}


async def m001_extension_settings(db):
    """
    Initial settings table.
    """

    await db.execute(
        f"""
        CREATE TABLE xero_sync.extension_settings (
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

    await db.execute(
        f"""
        CREATE TABLE xero_sync.wallets (
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
    is_pg = getattr(db, "type", "").upper() == "POSTGRES"
    tbl = "xero_sync.wallets" if is_pg else "wallets"
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

    is_pg = getattr(db, "type", "").upper() == "POSTGRES"
    connections_tbl = (
        "xero_sync.connections" if is_pg else "connections"
    )

    # Create table
    await db.execute(
        f"""
        CREATE TABLE {connections_tbl} (
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
        ON {connections_tbl} (user_id);
        """
    )
