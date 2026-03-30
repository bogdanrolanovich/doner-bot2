"""
Клавиатуры и кнопки бота
Все inline и reply-клавиатуры собраны в одном месте
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ─────────────────────────────────────────────
# Главное меню (два раздела)
# ─────────────────────────────────────────────
def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Кнопки «Меню» и «Отзывы» на главном экране"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🌯 Меню", callback_data="open_menu")
    builder.button(text="⭐ Отзывы", callback_data="open_reviews")
    builder.adjust(2)  # два столбца рядом
    return builder.as_markup()


# ─────────────────────────────────────────────
# Меню блюд
# ─────────────────────────────────────────────

# Данные о позициях: (название, цена, callback_data)
MENU_ITEMS = [
    ("🌯 Донер с курицей",  "250", "item_doner_chicken"),
    ("🥩 Донер с говядиной", "300", "item_doner_beef"),
    ("🍟 Картошка фри",     "120", "item_fries"),
    ("🍗 Наггетсы",         "150", "item_nuggets"),
]


def menu_keyboard() -> InlineKeyboardMarkup:
    """Список блюд — каждое блюдо отдельной кнопкой"""
    builder = InlineKeyboardBuilder()
    for name, price, cb in MENU_ITEMS:
        builder.button(text=f"{name} — {price}₽", callback_data=cb)
    builder.button(text="◀️ Назад", callback_data="back_to_start")
    builder.adjust(1)  # одна колонка, как у настоящего меню
    return builder.as_markup()


def dish_keyboard(item_cb: str) -> InlineKeyboardMarkup:
    """Кнопки для страницы конкретного блюда"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🛒 Добавить в заказ", callback_data=f"add_{item_cb}")
    builder.button(text="◀️ Назад в меню",    callback_data="open_menu")
    builder.adjust(1)
    return builder.as_markup()


# ─────────────────────────────────────────────
# Корзина / оформление заказа
# ─────────────────────────────────────────────
def cart_keyboard() -> InlineKeyboardMarkup:
    """Действия с корзиной"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Оформить заказ",   callback_data="checkout")
    builder.button(text="🗑 Очистить корзину",  callback_data="clear_cart")
    builder.button(text="◀️ Продолжить покупки", callback_data="open_menu")
    builder.adjust(1)
    return builder.as_markup()


def back_to_start_keyboard() -> InlineKeyboardMarkup:
    """Просто кнопка «Назад в главное меню»"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 Главное меню", callback_data="back_to_start")
    return builder.as_markup()


# ─────────────────────────────────────────────
# Отзывы
# ─────────────────────────────────────────────
def reviews_keyboard() -> InlineKeyboardMarkup:
    """Кнопки раздела отзывов"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✍️ Оставить отзыв", callback_data="write_review")
    builder.button(text="📋 Последние отзывы", callback_data="show_reviews")
    builder.button(text="◀️ Назад",           callback_data="back_to_start")
    builder.adjust(1)
    return builder.as_markup()


# ─────────────────────────────────────────────
# Доставка / оплата
# ─────────────────────────────────────────────
def delivery_keyboard() -> InlineKeyboardMarkup:
    """Кнопки: доставка или самовывоз"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🚚 Доставка", callback_data="choose_delivery")
    builder.button(text="🏃‍♂️ Самовывоз", callback_data="choose_pickup")
    builder.adjust(1)
    return builder.as_markup()


def payment_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Кнопка подтверждения оплаты для пользователя"""
    builder = InlineKeyboardBuilder()
    builder.button(text="Я оплатил", callback_data=f"paid_pending_{order_id}")
    builder.button(text="◀️ Назад", callback_data="back_to_start")
    builder.adjust(1)
    return builder.as_markup()
