"""
Состояния FSM (машина состояний)
Нужны чтобы бот «помнил» на каком шаге находится пользователь
"""

from aiogram.fsm.state import State, StatesGroup


class ReviewState(StatesGroup):
    """Состояния при написании отзыва"""
    waiting_for_text = State()   # ждём, когда пользователь напишет отзыв


class OrderState(StatesGroup):
    """Состояния при оформлении заказа"""
    browsing   = State()   # пользователь листает меню
    in_cart    = State()   # корзина открыта
    confirming = State()   # подтверждение заказа
    waiting_for_address = State()  # ждём, когда пользователь пришлёт адрес для доставки
