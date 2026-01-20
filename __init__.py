import asyncio

from fastapi import APIRouter
from lnbits.tasks import create_permanent_unique_task
from loguru import logger

from .crud import db
from .tasks import wait_for_paid_invoices
from .views import xerosync_generic_router
from .views_api import xerosync_api_router

xerosync_ext: APIRouter = APIRouter(prefix="/xerosync", tags=["XeroSync"])
xerosync_ext.include_router(xerosync_generic_router)
xerosync_ext.include_router(xerosync_api_router)


xerosync_static_files = [
    {
        "path": "/xerosync/static",
        "name": "xerosync_static",
    }
]

scheduled_tasks: list[asyncio.Task] = []


def xerosync_stop():
    for task in scheduled_tasks:
        try:
            task.cancel()
        except Exception as ex:
            logger.warning(ex)


def xerosync_start():
    task = create_permanent_unique_task("ext_xerosync", wait_for_paid_invoices)
    scheduled_tasks.append(task)


__all__ = [
    "db",
    "xerosync_ext",
    "xerosync_start",
    "xerosync_static_files",
    "xerosync_stop",
]
