"""Quản lý kết nối Prisma — singleton Store cho toàn app."""

from __future__ import annotations

from app.services.store import Store

_store: Store | None = None


def get_store() -> Store:
    """Lấy instance Store dùng chung."""
    global _store
    if _store is None:
        _store = Store()
    return _store


async def connect_db() -> None:
    """Kết nối database khi app khởi động."""
    await get_store().connect()


async def disconnect_db() -> None:
    """Đóng kết nối database khi app tắt."""
    await get_store().disconnect()
