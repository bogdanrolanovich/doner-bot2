"""
Telegram-бот для донерной
Стек: aiogram 3.x + SQLite
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import init_db
from handlers import router

# Настройка логирования — будем видеть все события в консоли
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    # Инициализируем базу данных (создаём таблицы если их нет)
    await init_db()
    logger.info("База данных инициализирована")

    # Создаём объект бота с токеном из конфига
    bot = Bot(token=BOT_TOKEN)

    # Dispatcher управляет обработчиками и FSM (машиной состояний)
    dp = Dispatcher(storage=MemoryStorage())

    # Подключаем все роуты (обработчики) из handlers.py
    dp.include_router(router)

    logger.info("Бот запущен. Нажмите Ctrl+C для остановки.")

    # Запускаем polling — бот будет опрашивать сервер Telegram на наличие сообщений
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
