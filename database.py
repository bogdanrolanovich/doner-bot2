"""
Работа с базой данных SQLite
Таблицы: orders (заказы), reviews (отзывы)
"""

import aiosqlite
import logging

logger = logging.getLogger(__name__)

# Путь к файлу базы данных
DB_PATH = "doner_bot.db"


async def init_db():
    """Создаёт таблицы при первом запуске, если их ещё нет"""
    async with aiosqlite.connect(DB_PATH) as db:

        # Таблица заказов (с возможностью статуса и типа доставки)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id           INTEGER NOT NULL,
                username          TEXT,
                items             TEXT NOT NULL,       -- список позиций через запятую
                total_price       INTEGER NOT NULL,    -- сумма в рублях
                delivery_type     TEXT,                -- "Доставка" или "Самовывоз"
                address           TEXT,                -- адрес доставки (если есть)
                status            TEXT DEFAULT 'pending', -- pending, awaiting_verification, confirmed, rejected
                payment_confirmed INTEGER DEFAULT 0,
                created_at        DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Таблица отзывов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                username    TEXT,
                text        TEXT NOT NULL,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.commit()
        # Выполняем простую миграцию: если база уже существовала, добавляем недостающие колонки
        async with db.execute("PRAGMA table_info(orders)") as cursor:
            rows = await cursor.fetchall()
        existing_cols = [row[1] for row in rows]

        if "delivery_type" not in existing_cols:
            await db.execute("ALTER TABLE orders ADD COLUMN delivery_type TEXT")
        if "address" not in existing_cols:
            await db.execute("ALTER TABLE orders ADD COLUMN address TEXT")
        if "status" not in existing_cols:
            await db.execute("ALTER TABLE orders ADD COLUMN status TEXT DEFAULT 'pending'")
        if "payment_confirmed" not in existing_cols:
            await db.execute("ALTER TABLE orders ADD COLUMN payment_confirmed INTEGER DEFAULT 0")

        await db.commit()
    logger.info("Таблицы БД готовы (миграция выполнена)")

    # Создаём таблицу для временных (ожидающих) заказов
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pending_orders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                username    TEXT,
                items       TEXT NOT NULL,
                total_price INTEGER NOT NULL,
                delivery_type TEXT,
                address     TEXT,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()
        # Если таблица уже существовала, убедимся, что в ней есть колонка address
        async with db.execute("PRAGMA table_info(pending_orders)") as cursor:
            rows = await cursor.fetchall()
        pending_cols = [row[1] for row in rows]
        if "address" not in pending_cols:
            await db.execute("ALTER TABLE pending_orders ADD COLUMN address TEXT")
            await db.commit()
    logger.info("Таблица pending_orders готова")


async def save_order(user_id: int, username: str, items: list[str], total: int, delivery_type: str = None, address: str | None = None) -> int:
    """Сохраняет новый заказ в базу данных и возвращает id заказа"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO orders (user_id, username, items, total_price, delivery_type, address) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username or "unknown", ", ".join(items), total, delivery_type, address)
        )
        await db.commit()
        order_id = cursor.lastrowid
    logger.info(f"Заказ сохранён: id={order_id}, user={user_id}, items={items}, total={total}")
    return order_id


async def save_pending_order(user_id: int, username: str, items: list[str], total: int, delivery_type: str = None, address: str | None = None) -> int:
    """Сохраняет временный заказ (пока не оплачен) и возвращает его id"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO pending_orders (user_id, username, items, total_price, delivery_type, address) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username or "unknown", ", ".join(items), total, delivery_type, address)
        )
        await db.commit()
        pending_id = cursor.lastrowid
    logger.info(f"Pending order saved: id={pending_id}, user={user_id}, total={total}")
    return pending_id


async def get_pending_order(pending_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM pending_orders WHERE id = ?", (pending_id,)) as cursor:
            row = await cursor.fetchone()
    return dict(row) if row else None


async def list_pending_orders() -> list[dict]:
    """Возвращает список всех pending_orders (по умолчанию последние 100)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, user_id, username, items, total_price, delivery_type, address, created_at FROM pending_orders ORDER BY id DESC LIMIT 100"
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def find_pending_by_user_and_total(user_id: int | None, username: str | None, total: int) -> dict | None:
    """Пытается найти pending-order по user_id или username и сумме. Возвращает первую найденную запись."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if user_id:
            async with db.execute(
                "SELECT * FROM pending_orders WHERE user_id = ? AND total_price = ? ORDER BY id DESC LIMIT 1",
                (user_id, total)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)

        if username:
            async with db.execute(
                "SELECT * FROM pending_orders WHERE username = ? AND total_price = ? ORDER BY id DESC LIMIT 1",
                (username, total)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)

    return None


async def delete_pending_order(pending_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM pending_orders WHERE id = ?", (pending_id,))
        await db.commit()
    logger.info(f"Pending order deleted: id={pending_id}")


async def confirm_pending_order(pending_id: int) -> int | None:
    """Переносит pending_order в таблицу orders и возвращает новый id заказа"""
    pending = await get_pending_order(pending_id)
    if not pending:
        return None

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO orders (user_id, username, items, total_price, delivery_type, address, status, payment_confirmed) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (pending['user_id'], pending['username'], pending['items'], pending['total_price'], pending['delivery_type'], pending.get('address'), 'confirmed', 1)
        )
        await db.execute("DELETE FROM pending_orders WHERE id = ?", (pending_id,))
        await db.commit()
        order_id = cursor.lastrowid
    logger.info(f"Pending order {pending_id} confirmed as order {order_id}")

    # Экспортируем подтверждённый заказ в CSV (можно открыть в Excel)
    try:
        order = await get_order_by_id(order_id)
        if order:
            await export_order_to_csv(order)
    except Exception:
        logger.exception("Ошибка при экспорте заказа в CSV")

    return order_id


async def export_order_to_csv(order: dict, path: str = "orders_export.csv"):
    """Добавляет строку заказа в CSV-файл (совместим с Excel)."""
    import csv
    from pathlib import Path
    from datetime import datetime

    file = Path(path)
    write_header = not file.exists()

    # Нормализуем поля
    row = {
        "id": order.get("id"),
        "user_id": order.get("user_id"),
        "username": order.get("username"),
        "items": order.get("items"),
        "total_price": order.get("total_price"),
        "delivery_type": order.get("delivery_type"),
        "address": order.get("address"),
        "created_at": order.get("created_at") or datetime.now().isoformat()
    }

    with file.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)


async def get_daily_revenue(date_str: str | None = None) -> int:
    """Возвращает сумму подтверждённых заказов за указанный день (формат YYYY-MM-DD). По умолчанию — сегодня."""
    if date_str is None:
        date_str = "'now'"
        date_clause = "DATE(created_at) = DATE('now','localtime')"
    else:
        date_clause = "DATE(created_at) = ?"

    async with aiosqlite.connect(DB_PATH) as db:
        if date_str == "'now'":
            async with db.execute(f"SELECT SUM(total_price) as total FROM orders WHERE {date_clause}") as cursor:
                row = await cursor.fetchone()
        else:
            async with db.execute("SELECT SUM(total_price) as total FROM orders WHERE DATE(created_at) = ?", (date_str,)) as cursor:
                row = await cursor.fetchone()
    total = row[0] if row and row[0] is not None else 0
    return total



async def save_review(user_id: int, username: str, text: str):
    """Сохраняет отзыв пользователя"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO reviews (user_id, username, text) VALUES (?, ?, ?)",
            (user_id, username or "unknown", text)
        )
        await db.commit()
    logger.info(f"Отзыв сохранён: user={user_id}")


async def get_last_reviews(limit: int = 5) -> list[dict]:
    """Возвращает последние N отзывов из базы"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT username, text, created_at FROM reviews ORDER BY id DESC LIMIT ?",
            (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def update_order_status(order_id: int, status: str, payment_confirmed: int | None = None):
    """Обновляет статус заказа, опционально помечает оплату подтверждённой"""
    async with aiosqlite.connect(DB_PATH) as db:
        if payment_confirmed is None:
            await db.execute(
                "UPDATE orders SET status = ? WHERE id = ?",
                (status, order_id)
            )
        else:
            await db.execute(
                "UPDATE orders SET status = ?, payment_confirmed = ? WHERE id = ?",
                (status, int(payment_confirmed), order_id)
            )
        await db.commit()
    logger.info(f"Order {order_id} updated: status={status}, payment_confirmed={payment_confirmed}")


async def get_order_by_id(order_id: int) -> dict | None:
    """Возвращает заказ по id или None"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM orders WHERE id = ?",
            (order_id,)
        ) as cursor:
            row = await cursor.fetchone()
    return dict(row) if row else None
