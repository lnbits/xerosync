import asyncio

from lnbits.core.models import Payment
from lnbits.tasks import register_invoice_listener
from loguru import logger

from .services import payment_received_for_client_data
from .crud import get_wallet_by_wallet_id, get_xero_connection

async def wait_for_paid_invoices():
    invoice_queue = asyncio.Queue()
    register_invoice_listener(invoice_queue, "ext_xero_sync")
    while True:
        payment = await invoice_queue.get()
        await on_invoice_paid(payment)


async def on_invoice_paid(payment: Payment) -> None:
    wallet_cfg = await get_wallet_by_wallet_id(payment.wallet_id)
    if not wallet_cfg:
        return
    logger.debug(f"Xero Sync: Processing payment for wallet {payment.wallet_id}")
    logger.debug(payment)
    conn = await get_xero_connection(wallet_cfg.user_id)
    if not conn:
        logger.warning("Xero Sync: no Xero connection for user, skipping")
        return
    try:
        await payment_received_for_client_data(payment, conn, wallet_cfg)
    except Exception as e:
        logger.error(f"Error processing payment for xero_sync: {e}")
