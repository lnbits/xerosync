from http import HTTPStatus

from fastapi import APIRouter, Depends
from fastapi.exceptions import HTTPException
from lnbits.core.models import SimpleStatus, User
from lnbits.db import Filters, Page
from lnbits.decorators import (
    check_user_exists,
    parse_filters,
)
from lnbits.helpers import generate_filter_params_openapi

from .crud import (
    create_wallets,
    delete_wallets,
    get_wallets,
    get_wallets_paginated,
    update_wallets,
    get_xero_connection,
)
from .models import (
    CreateWallets,
    ExtensionSettings,  #
    Wallets,
    WalletsFilters,
)
from .services import (
    get_settings,  #
    update_settings,  #
    sync_wallet_payments,
    ensure_xero_access_token,
    fetch_xero_accounts,
    fetch_xero_bank_accounts,
)

wallets_filters = parse_filters(WalletsFilters)

xero_sync_api_router = APIRouter()


############################# Wallets #############################
@xero_sync_api_router.post("/api/v1/wallets", status_code=HTTPStatus.CREATED)
async def api_create_wallets(
    data: CreateWallets,
    user: User = Depends(check_user_exists),
) -> Wallets:
    wallets = await create_wallets(user.id, data)
    return wallets


@xero_sync_api_router.put("/api/v1/wallets/{wallets_id}", status_code=HTTPStatus.CREATED)
async def api_update_wallets(
    wallets_id: str,
    data: CreateWallets,
    user: User = Depends(check_user_exists),
) -> Wallets:
    wallets = await get_wallets(user.id, wallets_id)
    if not wallets:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Wallets not found.")
    if wallets.user_id != user.id:
        raise HTTPException(HTTPStatus.FORBIDDEN, "You do not own this wallets.")
    wallets = await update_wallets(Wallets(**{**wallets.dict(), **data.dict()}))
    return wallets


@xero_sync_api_router.get(
    "/api/v1/wallets/paginated",
    name="Wallets List",
    summary="get paginated list of wallets",
    response_description="list of wallets",
    openapi_extra=generate_filter_params_openapi(WalletsFilters),
    response_model=Page[Wallets],
)
async def api_get_wallets_paginated(
    user: User = Depends(check_user_exists),
    filters: Filters = Depends(wallets_filters),
) -> Page[Wallets]:

    return await get_wallets_paginated(
        user_id=user.id,
        filters=filters,
    )


@xero_sync_api_router.get(
    "/api/v1/wallets/{wallets_id}",
    name="Get Wallets",
    summary="Get the wallets with this id.",
    response_description="An wallets or 404 if not found",
    response_model=Wallets,
)
async def api_get_wallets(
    wallets_id: str,
    user: User = Depends(check_user_exists),
) -> Wallets:

    wallets = await get_wallets(user.id, wallets_id)
    if not wallets:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Wallets not found.")

    return wallets


@xero_sync_api_router.delete(
    "/api/v1/wallets/{wallets_id}",
    name="Delete Wallets",
    summary="Delete the wallets " "and optionally all its associated client_data.",
    response_description="The status of the deletion.",
    response_model=SimpleStatus,
)
async def api_delete_wallets(
    wallets_id: str,
    clear_client_data: bool | None = False,
    user: User = Depends(check_user_exists),
) -> SimpleStatus:

    await delete_wallets(user.id, wallets_id)
    if clear_client_data is True:
        # await delete all client data associated with this wallets
        pass
    return SimpleStatus(success=True, message="Wallets Deleted")


@xero_sync_api_router.post(
    "/api/v1/wallets/{wallets_id}/push",
    name="Push Wallet Payments",
    summary="Push all current successful incoming payments to Xero.",
    response_description="Push status summary.",
    response_model=SimpleStatus,
)
async def api_push_wallets(
    wallets_id: str,
    user: User = Depends(check_user_exists),
) -> SimpleStatus:
    wallets = await get_wallets(user.id, wallets_id)
    if not wallets:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Wallets not found.")
    if wallets.user_id != user.id:
        raise HTTPException(HTTPStatus.FORBIDDEN, "You do not own this wallets.")

    try:
        summary = await sync_wallet_payments(wallets)
    except RuntimeError as exc:
        raise HTTPException(HTTPStatus.BAD_REQUEST, str(exc))

    message = (
        f"Pushed {summary['pushed']} payment(s); "
        f"skipped {summary['skipped']}; "
        f"failed {summary['failed']}."
    )
    if summary.get("errors"):
        message += f" Errors: {', '.join(summary['errors'])}"
    return SimpleStatus(success=True, message=message)


############################ Xero Metadata #############################
@xero_sync_api_router.get(
    "/api/v1/accounts",
    name="List Xero Accounts",
    summary="Fetch chart of accounts from Xero for this user.",
)
async def api_get_accounts(user: User = Depends(check_user_exists)):
    conn = await get_xero_connection(user.id)
    if not conn:
        raise HTTPException(
            HTTPStatus.BAD_REQUEST, "No Xero connection configured for this user."
        )
    settings = await get_settings(user.id)
    access_token, tenant_id = await ensure_xero_access_token(conn, settings)
    accounts = await fetch_xero_accounts(access_token, tenant_id)
    # Return minimal shape for selects
    return [
        {
            "value": acc.get("Code") or acc.get("AccountID"),
            "label": f"{acc.get('Code') or ''} – {acc.get('Name') or ''}".strip(" –"),
            "type": acc.get("Type"),
        }
        for acc in accounts
    ]


@xero_sync_api_router.get(
    "/api/v1/bank_accounts",
    name="List Xero Bank Accounts",
    summary="Fetch bank accounts from Xero for this user.",
)
async def api_get_bank_accounts(user: User = Depends(check_user_exists)):
    conn = await get_xero_connection(user.id)
    if not conn:
        raise HTTPException(
            HTTPStatus.BAD_REQUEST, "No Xero connection configured for this user."
        )
    settings = await get_settings(user.id)
    access_token, tenant_id = await ensure_xero_access_token(conn, settings)
    banks = await fetch_xero_bank_accounts(access_token, tenant_id)
    return [
        {
            "value": acc.get("AccountID"),
            "label": f"{acc.get('Name') or ''} ({acc.get('AccountNumber') or ''})".strip(),
        }
        for acc in banks
    ]


############################ Settings #############################
@xero_sync_api_router.get(
    "/api/v1/settings",
    name="Get Settings",
    summary="Get the settings for the current user.",
    response_description="The settings or 404 if not found",
    response_model=ExtensionSettings,
)
async def api_get_settings(
    user: User = Depends(check_user_exists),
) -> ExtensionSettings:
    user_id = "admin" if ExtensionSettings.is_admin_only() else user.id
    return await get_settings(user_id)


@xero_sync_api_router.put(
    "/api/v1/settings",
    name="Update Settings",
    summary="Update the settings for the current user.",
    response_description="The updated settings.",
    response_model=ExtensionSettings,
)
async def api_update_extension_settings(
    data: ExtensionSettings,
    user: User = Depends(check_user_exists),
) -> ExtensionSettings:
    if ExtensionSettings.is_admin_only() and not user.admin:
        raise HTTPException(
            HTTPStatus.FORBIDDEN,
            "Only admins can update settings.",
        )
    user_id = "admin" if ExtensionSettings.is_admin_only() else user.id
    return await update_settings(user_id, data)
