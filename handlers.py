"""
Обработчики всех команд и нажатий кнопок
Это «сердце» бота — здесь вся логика
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from config import RESTAURANT_NAME, CONTACT_INFO, ADMIN_ID, ADMIN_CHAT_ID, ADMIN_USER_ID, KASPI_NUMBER, HALYK_CARD
from database import (
    save_order, save_review, get_last_reviews, update_order_status, get_order_by_id,
    save_pending_order, get_pending_order, confirm_pending_order, delete_pending_order, get_daily_revenue,
    list_pending_orders, find_pending_by_user_and_total
)
from keyboards import (
    main_menu_keyboard, menu_keyboard, dish_keyboard,
    cart_keyboard, back_to_start_keyboard, reviews_keyboard,
    MENU_ITEMS, delivery_keyboard, payment_keyboard
)
from states import ReviewState, OrderState

# Все обработчики регистрируются через один роутер
router = Router()

# ─── Словарь блюд для быстрого поиска по callback_data ───────────────────────
# Формат: callback_data -> (название, цена)
DISHES = {item[2]: (item[0], int(item[1])) for item in MENU_ITEMS}
# Например: "item_doner_chicken" -> ("🌯 Донер с курицей", 250)


# ═════════════════════════════════════════════════════════════════════════════
# /start — приветствие
# ═════════════════════════════════════════════════════════════════════════════
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Отправляем приветствие с описанием заведения и двумя кнопками"""

    # Сбрасываем любое предыдущее состояние пользователя
    await state.clear()

    # Имя пользователя для персонального обращения
    user_name = message.from_user.first_name or "Гость"

    welcome_text = (
        f"👋 Привет, {user_name}!\n\n"
        f"Добро пожаловать в <b>{RESTAURANT_NAME}</b>! 🌯\n\n"
        "Мы готовим вкуснейшие донеры, хрустящую картошку фри "
        "и сочные наггетсы из свежих ингредиентов каждый день.\n\n"
        "Что хотите сделать?"
    )

    await message.answer(
        welcome_text,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard()
    )


@router.message(Command("revenue"))
async def cmd_revenue(message: Message):
    """Показать сумму подтверждённых заказов за сегодня (только админ)"""
    if message.from_user.id != ADMIN_USER_ID:
        await message.answer("У вас нет прав для этой команды.")
        return

    total = await get_daily_revenue()
    await message.answer(f"📅 Доход за сегодня: <b>{total}₽</b>", parse_mode="HTML")


# ═════════════════════════════════════════════════════════════════════════════
# Кнопка «Назад в главное меню»
# ═════════════════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "back_to_start")
async def back_to_start(callback: CallbackQuery, state: FSMContext):
    """Возвращаемся на главный экран и сбрасываем состояние"""
    await state.clear()
    await callback.message.edit_text(
        f"🏠 Главное меню <b>{RESTAURANT_NAME}</b>\n\nЧто хотите сделать?",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()


# ═════════════════════════════════════════════════════════════════════════════
# РАЗДЕЛ МЕНЮ
# ═════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "open_menu")
async def show_menu(callback: CallbackQuery, state: FSMContext):
    """Показываем список всех блюд"""
    await state.set_state(OrderState.browsing)

    # Читаем корзину из данных состояния (пустой список если нет)
    data = await state.get_data()
    cart = data.get("cart", [])
    cart_hint = f"\n\n🛒 В корзине: {len(cart)} поз." if cart else ""

    await callback.message.edit_text(
        f"🍽 <b>Наше меню</b>{cart_hint}\n\nВыберите блюдо:",
        parse_mode="HTML",
        reply_markup=menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("item_"))
async def show_dish(callback: CallbackQuery):
    """Показываем страницу конкретного блюда с описанием и кнопкой «добавить»"""
    item_cb = callback.data  # например "item_doner_chicken"
    name, price = DISHES[item_cb]

    # Описания блюд
    descriptions = {
        "item_doner_chicken":  "Нежное куриное филе, свежие овощи, фирменный соус в лаваше.",
        "item_doner_beef":     "Сочная говядина на гриле, маринованный лук, зелень и томаты.",
        "item_fries":          "Золотистые ломтики картофеля, хрустящие снаружи и мягкие внутри.",
        "item_nuggets":        "Куриные наггетсы в панировке — идеально к донеру или отдельно.",
    }
    desc = descriptions.get(item_cb, "Вкусное блюдо из нашего меню.")

    await callback.message.edit_text(
        f"{name}\n\n{desc}\n\n💰 Цена: <b>{price}₽</b>",
        parse_mode="HTML",
        reply_markup=dish_keyboard(item_cb)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("add_item_"))
async def add_to_cart(callback: CallbackQuery, state: FSMContext):
    """Добавляем блюдо в корзину (хранится в FSM-данных пользователя)"""
    # callback.data = "add_item_doner_chicken" → убираем "add_" → "item_doner_chicken"
    item_cb = callback.data[4:]
    name, price = DISHES[item_cb]

    # Загружаем текущую корзину из состояния
    data = await state.get_data()
    cart: list = data.get("cart", [])

    # Добавляем позицию (храним как кортеж: название + цена)
    cart.append({"name": name, "price": price})
    await state.update_data(cart=cart)

    await callback.answer(f"✅ {name} добавлен в корзину!", show_alert=False)

    # Считаем итоговую сумму и показываем корзину
    total = sum(item["price"] for item in cart)
    items_text = "\n".join(f"• {item['name']} — {item['price']}₽" for item in cart)

    await callback.message.edit_text(
        f"🛒 <b>Ваша корзина:</b>\n\n{items_text}\n\n"
        f"💰 <b>Итого: {total}₽</b>",
        parse_mode="HTML",
        reply_markup=cart_keyboard()
    )
    await state.set_state(OrderState.in_cart)


@router.callback_query(F.data == "clear_cart")
async def clear_cart(callback: CallbackQuery, state: FSMContext):
    """Очищаем корзину и возвращаемся в меню"""
    await state.update_data(cart=[])
    await callback.answer("🗑 Корзина очищена")
    await show_menu(callback, state)


@router.callback_query(F.data == "checkout")
async def checkout(callback: CallbackQuery, state: FSMContext):
    """Переходим к подтверждению: просим выбрать доставка/самовывоз"""
    data = await state.get_data()
    cart: list = data.get("cart", [])

    if not cart:
        await callback.answer("❌ Корзина пуста!", show_alert=True)
        return

    # Считаем итог и переводим пользователя в режим подтверждения
    total = sum(item["price"] for item in cart)
    items_names = [item["name"] for item in cart]

    items_text = "\n".join(f"• {name}" for name in items_names)
    await state.set_state(OrderState.confirming)

    await callback.message.edit_text(
        f"🧾 <b>Подтвердите заказ</b>\n\n"
        f"Вы заказали:\n{items_text}\n\n"
        f"💰 Сумма: <b>{total}₽</b>\n\n"
        f"Выберите способ получения:",
        parse_mode="HTML",
        reply_markup=delivery_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "choose_delivery")
@router.callback_query(F.data == "choose_pickup")
async def choose_delivery_pickup(callback: CallbackQuery, state: FSMContext):
    """Сохраняем заказ и показываем пользователю платёжную инструкцию с кнопкой 'Я оплатил'"""
    choice = callback.data
    delivery_type = "Доставка" if choice == "choose_delivery" else "Самовывоз"

    data = await state.get_data()
    cart: list = data.get("cart", [])
    if not cart:
        await callback.answer("❌ Корзина пуста!", show_alert=True)
        return

    total = sum(item["price"] for item in cart)
    items_names = [item["name"] for item in cart]

    user = callback.from_user

    # Если выбран самовывоз — сразу сохраняем pending и показываем оплату
    if delivery_type == "Самовывоз":
        pending_id = await save_pending_order(
            user_id=user.id,
            username=user.username,
            items=items_names,
            total=total,
            delivery_type=delivery_type,
            address=None
        )

        # Очищаем состояние пользователя
        await state.clear()

        payment_text = (
            f"💳 Оплатите, пожалуйста, одним из способов:\n\n"
            f"• Kaspi Pay по номеру: <b>{KASPI_NUMBER}</b>\n"
            f"• Halyk (карта): <b>{HALYK_CARD}</b>\n\n"
            f"После оплаты нажмите «Я оплатил», и администратор проверит платёж вручную.\n"
            f"Номер заказа: <b>#{pending_id}</b>"
        )

        await callback.message.edit_text(
            payment_text,
            parse_mode="HTML",
            reply_markup=payment_keyboard(pending_id)
        )
        await callback.answer()
        return

    # Для доставки — просим пользователя прислать город и адрес
    await state.update_data(cart=cart, delivery_type=delivery_type, total=total)
    await state.set_state(OrderState.waiting_for_address)
    await callback.message.edit_text(
        "📍 Пожалуйста, введите город и полный адрес доставки одним сообщением:\n\nНапример: Москва, ул. Ленина, д. 1, кв. 5",
        parse_mode="HTML",
        reply_markup=back_to_start_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("paid_pending_"))
async def user_clicked_paid(callback: CallbackQuery):
    """Пользователь нажал «Я оплатил» — отправляем уведомление админу для проверки"""
    try:
        pending_id = int(callback.data.rsplit("_", 1)[1])
    except Exception:
        await callback.answer(f"Некорректный идентификатор заказа. Данные: {callback.data}")
        return

    order = await get_pending_order(pending_id)
    if not order:
        await callback.answer("Ошибка: заказ не найден.")
        return

    items = order.get("items", "")
    total = order.get("total_price", 0)
    user_display = f"@{order['username']}" if order.get('username') else str(order['user_id'])

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить оплату", callback_data=f"admin_confirm_pending_{pending_id}")
    kb.button(text="❌ Отклонить", callback_data=f"admin_reject_pending_{pending_id}")
    kb.adjust(2)

    admin_msg = (
        f"Поступил платёж для проверки:\n\n"
        f"Заказ: <b>#{pending_id}</b>\n"
        f"Пользователь: {user_display}\n"
        f"Сумма: <b>{total}₽</b>\n"
        f"Позиции:\n{items}\n"
        f"Тип: {order.get('delivery_type') or '-'}\n"
        f"Адрес: {order.get('address') or '-'}"
    )

    bot = callback.message.bot
    target_chat = ADMIN_CHAT_ID if ADMIN_CHAT_ID is not None else ADMIN_ID
    if target_chat and target_chat != 0:
        try:
            await bot.send_message(target_chat, admin_msg, parse_mode="HTML", reply_markup=kb.as_markup())
            await callback.answer("✅ Спасибо — администратор проверит платёж.")
            await callback.message.edit_text("✅ Спасибо, мы сообщили администратору. Ожидайте проверки.")
        except TelegramBadRequest:
            await callback.answer("Оплата отмечена, но не удалось уведомить администратора.", show_alert=True)
            await callback.message.edit_text("✅ Спасибо, оплата отмечена. Администратор недоступен.")
    else:
        await callback.answer("Оплата отмечена, но администратор не настроен.", show_alert=True)


@router.message(OrderState.waiting_for_address)
async def receive_address(message: Message, state: FSMContext):
    """При оформлении доставки принимаем адрес от пользователя и создаём pending заказ"""
    address = message.text.strip()
    if len(address) < 5:
        await message.answer("Пожалуйста, укажите корректный адрес (город и улицу).")
        return

    data = await state.get_data()
    cart: list = data.get("cart", [])
    delivery_type = data.get("delivery_type", "Доставка")
    total = data.get("total")

    if not cart or total is None:
        await message.answer("Ошибка: корзина пуста или данные утеряны. Пожалуйста, начните заново.")
        await state.clear()
        return

    items_names = [item["name"] for item in cart]
    pending_id = await save_pending_order(
        user_id=message.from_user.id,
        username=message.from_user.username,
        items=items_names,
        total=total,
        delivery_type=delivery_type,
        address=address
    )

    await state.clear()

    payment_text = (
        f"💳 Оплатите, пожалуйста, одним из способов:\n\n"
        f"• Kaspi Pay по номеру: <b>{KASPI_NUMBER}</b>\n"
        f"• Halyk (карта): <b>{HALYK_CARD}</b>\n\n"
        f"После оплаты нажмите «Я оплатил», и администратор проверит платёж вручную.\n"
        f"Номер заказа: <b>#{pending_id}</b>"
    )

    await message.answer(payment_text, parse_mode="HTML", reply_markup=payment_keyboard(pending_id))


@router.callback_query(F.data.startswith("admin_confirm_pending_"))
async def admin_confirm_pending(callback: CallbackQuery):
    try:
        chat_id = callback.message.chat.id
    except Exception:
        chat_id = None

    if not ((ADMIN_CHAT_ID and chat_id == ADMIN_CHAT_ID) or (callback.from_user.id == ADMIN_USER_ID)):
        await callback.answer("У вас нет прав администратора.", show_alert=True)
        return

    try:
        pending_id = int(callback.data.rsplit("_", 1)[1])
    except Exception:
        await callback.answer(f"Некорректный идентификатор заказа. Данные: {callback.data}")
        return

    pending = await get_pending_order(pending_id)

    if not pending:
        text = callback.message.text or ""
        import re
        m = re.search(r"#(\d+)", text)
        if m:
            try:
                alt_id = int(m.group(1))
                pending = await get_pending_order(alt_id)
            except Exception:
                pending = None

        if not pending:
            nums = re.findall(r"(\d+)", text)
            for n in reversed(nums):
                try:
                    cand = int(n)
                    pending = await get_pending_order(cand)
                    if pending:
                        pending_id = cand
                        break
                except Exception:
                    continue

        if not pending:
            user_match = re.search(r"Пользователь:\s*(?:@?([A-Za-z0-9_]+)|([0-9]+))", text)
            total_match = re.search(r"Сумма:\s*<b>([0-9]+)₽</b>", text)
            u_name = None
            u_id = None
            total_val = None
            if user_match:
                if user_match.group(1):
                    u_name = user_match.group(1)
                elif user_match.group(2):
                    try:
                        u_id = int(user_match.group(2))
                    except Exception:
                        u_id = None
            if total_match:
                try:
                    total_val = int(total_match.group(1))
                except Exception:
                    total_val = None
            if total_val is not None:
                pending = await find_pending_by_user_and_total(u_id, u_name, total_val)

    if not pending:
        await callback.answer(f"Заказ не найден. callback.data: {callback.data}", show_alert=True)
        return

    try:
        actual_id = int(pending.get('id')) if pending.get('id') is not None else None
    except Exception:
        actual_id = None
    if actual_id:
        pending_id = actual_id

    new_order_id = await confirm_pending_order(pending_id)
    bot = callback.message.bot
    try:
        await bot.send_message(pending['user_id'], "🎉 Ваш заказ принят! Ожидайте, пожалуйста.")
    except Exception:
        pass

    await callback.answer("Оплата подтверждена.")
    await callback.message.edit_text(f"Pending #{pending_id} подтверждён и сохранён как заказ #{new_order_id}.")


@router.callback_query(F.data.startswith("admin_reject_pending_"))
async def admin_reject_pending(callback: CallbackQuery):
    try:
        chat_id = callback.message.chat.id
    except Exception:
        chat_id = None

    if not ((ADMIN_CHAT_ID and chat_id == ADMIN_CHAT_ID) or (callback.from_user.id == ADMIN_USER_ID)):
        await callback.answer("У вас нет прав администратора.", show_alert=True)
        return

    try:
        pending_id = int(callback.data.rsplit("_", 1)[1])
    except Exception:
        await callback.answer(f"Некорректный идентификатор заказа. Данные: {callback.data}")
        return

    pending = await get_pending_order(pending_id)
    if not pending:
        text = callback.message.text or ""
        import re
        m = re.search(r"#(\d+)", text)
        if m:
            try:
                alt_id = int(m.group(1))
                pending = await get_pending_order(alt_id)
                if pending:
                    pending_id = alt_id
            except Exception:
                pending = None

        if not pending:
            nums = re.findall(r"(\d+)", text)
            for n in reversed(nums):
                try:
                    cand = int(n)
                    pending = await get_pending_order(cand)
                    if pending:
                        pending_id = cand
                        break
                except Exception:
                    continue

    if not pending:
        await callback.answer(f"Заказ не найден. callback.data: {callback.data}", show_alert=True)
        return

    await delete_pending_order(pending_id)
    bot = callback.message.bot
    try:
        await bot.send_message(pending['user_id'], "❌ Платёж не подтверждён. Пожалуйста, свяжитесь с магазином.")
    except Exception:
        pass

    await callback.answer("Платёж отклонён.")
    await callback.message.edit_text(f"Pending #{pending_id} отклонён администратором.")


@router.callback_query(F.data.startswith("admin_confirm_"))
async def admin_confirm(callback: CallbackQuery):
    try:
        chat_id = callback.message.chat.id
    except Exception:
        chat_id = None

    if not ((ADMIN_CHAT_ID and chat_id == ADMIN_CHAT_ID) or (callback.from_user.id == ADMIN_USER_ID)):
        await callback.answer("У вас нет прав администратора.", show_alert=True)
        return

    try:
        order_id = int(callback.data.rsplit("_", 1)[1])
    except Exception:
        await callback.answer(f"Некорректный идентификатор заказа. Данные: {callback.data}")
        return

    order = await get_order_by_id(order_id)
    if not order:
        await callback.answer("Заказ не найден.")
        return

    await update_order_status(order_id, "confirmed", payment_confirmed=1)
    bot = callback.message.bot
    try:
        await bot.send_message(order['user_id'], "🎉 Ваш заказ принят! Ожидайте, пожалуйста.")
    except Exception:
        pass

    await callback.answer("Оплата подтверждена.")
    await callback.message.edit_text(f"Заказ #{order_id} подтверждён администратором.")


@router.callback_query(F.data.startswith("admin_reject_"))
async def admin_reject(callback: CallbackQuery):
    try:
        chat_id = callback.message.chat.id
    except Exception:
        chat_id = None

    if not ((ADMIN_CHAT_ID and chat_id == ADMIN_CHAT_ID) or (callback.from_user.id == ADMIN_USER_ID)):
        await callback.answer("У вас нет прав администратора.", show_alert=True)
        return

    try:
        order_id = int(callback.data.rsplit("_", 1)[1])
    except Exception:
        await callback.answer(f"Некорректный идентификатор заказа. Данные: {callback.data}")
        return

    order = await get_order_by_id(order_id)
    if not order:
        await callback.answer("Заказ не найден.")
        return

    await update_order_status(order_id, "rejected", payment_confirmed=0)
    bot = callback.message.bot
    try:
        await bot.send_message(order['user_id'], "❌ Платёж не подтверждён. Пожалуйста, свяжитесь с магазином.")
    except Exception:
        pass

    await callback.answer("Платёж отклонён.")
    await callback.message.edit_text(f"Заказ #{order_id} отклонён администратором.")

# ═════════════════════════════════════════════════════════════════════════════
# РАЗДЕЛ ОТЗЫВОВ
# ═════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "open_reviews")
async def show_reviews_menu(callback: CallbackQuery, state: FSMContext):
    """Главная страница раздела отзывов"""
    await state.clear()
    await callback.message.edit_text(
        "⭐ <b>Отзывы</b>\n\n"
        "Здесь вы можете прочитать отзывы наших гостей "
        "или поделиться своим мнением!",
        parse_mode="HTML",
        reply_markup=reviews_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "show_reviews")
async def show_last_reviews(callback: CallbackQuery):
    """Показываем последние 5 отзывов из базы"""
    reviews = await get_last_reviews(limit=5)

    if not reviews:
        text = "📭 Пока отзывов нет. Будьте первым!"
    else:
        lines = []
        for r in reviews:
            # Форматируем дату (2024-01-15 14:30:00 → 15.01.2024)
            date_str = r["created_at"][:10] if r["created_at"] else ""
            date_fmt = f"{date_str[8:10]}.{date_str[5:7]}.{date_str[:4]}" if date_str else ""
            username = f"@{r['username']}" if r["username"] else "Гость"
            lines.append(f"<b>{username}</b>  <i>{date_fmt}</i>\n{r['text']}")
        text = "⭐ <b>Последние отзывы:</b>\n\n" + "\n\n─────────\n\n".join(lines)

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=reviews_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "write_review")
async def start_writing_review(callback: CallbackQuery, state: FSMContext):
    """Переводим пользователя в режим ожидания текста отзыва"""
    await state.set_state(ReviewState.waiting_for_text)
    await callback.message.edit_text(
        "✍️ Напишите ваш отзыв следующим сообщением.\n\n"
        "Поделитесь впечатлениями о нашей еде и сервисе!\n\n"
        "<i>Для отмены введите /start</i>",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(ReviewState.waiting_for_text)
async def receive_review(message: Message, state: FSMContext):
    """Получаем текст отзыва от пользователя и сохраняем его"""
    review_text = message.text.strip()

    # Базовая валидация: слишком короткий отзыв не принимаем
    if len(review_text) < 5:
        await message.answer("❌ Отзыв слишком короткий. Пожалуйста, напишите подробнее!")
        return

    # Слишком длинный тоже обрезаем
    if len(review_text) > 1000:
        await message.answer("❌ Отзыв слишком длинный (максимум 1000 символов). Попробуйте сократить.")
        return

    # Сохраняем отзыв в базу данных
    user = message.from_user
    await save_review(
        user_id=user.id,
        username=user.username,
        text=review_text
    )

    # Выходим из состояния ожидания
    await state.clear()

    await message.answer(
        "🙏 <b>Спасибо за ваш отзыв!</b>\n\n"
        "Ваше мнение очень важно для нас.",
        parse_mode="HTML",
        reply_markup=back_to_start_keyboard()
    )


# ═════════════════════════════════════════════════════════════════════════════
# Обработчик любых неизвестных сообщений (fallback)
# ═════════════════════════════════════════════════════════════════════════════
@router.message()
async def fallback(message: Message):
    """Если пользователь написал что-то неожиданное — подсказываем что делать"""
    await message.answer(
        "Не понимаю эту команду 😅\n\nНапишите /start чтобы открыть главное меню.",
        reply_markup=back_to_start_keyboard()
    )


@router.message(Command("test_admin"))
async def cmd_test_admin(message: Message):
    """Команда для тестовой отправки сообщения в админ-чат (отладка)."""
    bot = message.bot
    target = ADMIN_CHAT_ID if ADMIN_CHAT_ID is not None else ADMIN_ID
    test_text = f"Тестовое уведомление от бота. Прислал: {message.from_user.id}"
    try:
        await bot.send_message(target, test_text)
        await message.answer("✅ Тестовое сообщение отправлено в админ-чат.")
    except Exception as e:
        await message.answer(f"❌ Не удалось отправить сообщение в админ-чат: {e}")


@router.message(Command("list_pending"))
async def cmd_list_pending(message: Message):
    """Показывает список ожидающих оплат (только админ‑чат или админ‑пользователь)."""
    try:
        chat_id = message.chat.id
    except Exception:
        chat_id = None

    if not ((ADMIN_CHAT_ID and chat_id == ADMIN_CHAT_ID) or (message.from_user.id == ADMIN_USER_ID)):
        await message.answer("У вас нет прав администратора.")
        return

    pendings = await list_pending_orders()
    if not pendings:
        await message.answer("Нет ожидающих платежей.")
        return

    lines = []
    for p in pendings:
        lines.append(f"#{p['id']} — {p.get('username') or p.get('user_id')} — {p.get('total_price')}₽ — {p.get('delivery_type') or '-'} — {p.get('address') or '-'}")

    text = "📋 Список pending-заказов (последние):\n\n" + "\n".join(lines)
    # отправляем в чат, откуда пришёл запрос
    await message.answer(text)


@router.message(Command("confirm_pending"))
async def cmd_confirm_pending(message: Message):
    """Админ-команда: подтвердить pending заказ по id: /confirm_pending 12"""
    try:
        chat_id = message.chat.id
    except Exception:
        chat_id = None
    if not ((ADMIN_CHAT_ID and chat_id == ADMIN_CHAT_ID) or (message.from_user.id == ADMIN_USER_ID)):
        await message.answer("У вас нет прав администратора.")
        return

    parts = message.text.strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /confirm_pending <id>")
        return
    pending_id = int(parts[1])
    pending = await get_pending_order(pending_id)
    if not pending:
        await message.answer("Заказ не найден.")
        return

    new_order_id = await confirm_pending_order(pending_id)
    await message.answer(f"Pending #{pending_id} подтвержён и сохранён как заказ #{new_order_id}.")
    try:
        await message.bot.send_message(pending['user_id'], f"🎉 Ваш платёж за заказ #{new_order_id} подтверждён. Ожидайте заказ.")
    except Exception:
        pass


@router.message(Command("reject_pending"))
async def cmd_reject_pending(message: Message):
    """Админ-команда: отклонить pending заказ по id: /reject_pending 12"""
    try:
        chat_id = message.chat.id
    except Exception:
        chat_id = None
    if not ((ADMIN_CHAT_ID and chat_id == ADMIN_CHAT_ID) or (message.from_user.id == ADMIN_USER_ID)):
        await message.answer("У вас нет прав администратора.")
        return

    parts = message.text.strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /reject_pending <id>")
        return
    pending_id = int(parts[1])
    pending = await get_pending_order(pending_id)
    if not pending:
        await message.answer("Заказ не найден.")
        return

    await delete_pending_order(pending_id)
    await message.answer(f"Pending #{pending_id} отклонён.")
    try:
        await message.bot.send_message(pending['user_id'], f"❌ Ваш платёж за pending #{pending_id} не подтверждён. Пожалуйста, свяжитесь с магазином.")
    except Exception:
        pass


@router.message(Command("confirm_order"))
async def cmd_confirm_order(message: Message):
    """Админ-команда: подтвердить существующий заказ по id: /confirm_order 5"""
    try:
        chat_id = message.chat.id
    except Exception:
        chat_id = None
    if not ((ADMIN_CHAT_ID and chat_id == ADMIN_CHAT_ID) or (message.from_user.id == ADMIN_USER_ID)):
        await message.answer("У вас нет прав администратора.")
        return

    parts = message.text.strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /confirm_order <id>")
        return
    order_id = int(parts[1])
    order = await get_order_by_id(order_id)
    if not order:
        await message.answer("Заказ не найден.")
        return

    await update_order_status(order_id, "confirmed", payment_confirmed=1)
    await message.answer(f"Заказ #{order_id} подтверждён.")
    try:
        await message.bot.send_message(order['user_id'], f"🎉 Ваш заказ #{order_id} подтверждён. Ожидайте, пожалуйста.")
    except Exception:
        pass


@router.message(Command("reject_order"))
async def cmd_reject_order(message: Message):
    """Админ-команда: отклонить существующий заказ по id: /reject_order 5"""
    try:
        chat_id = message.chat.id
    except Exception:
        chat_id = None
    if not ((ADMIN_CHAT_ID and chat_id == ADMIN_CHAT_ID) or (message.from_user.id == ADMIN_USER_ID)):
        await message.answer("У вас нет прав администратора.")
        return

    parts = message.text.strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /reject_order <id>")
        return
    order_id = int(parts[1])
    order = await get_order_by_id(order_id)
    if not order:
        await message.answer("Заказ не найден.")
        return

    await update_order_status(order_id, "rejected", payment_confirmed=0)
    await message.answer(f"Заказ #{order_id} отклонён.")
    try:
        await message.bot.send_message(order['user_id'], f"❌ Ваш заказ #{order_id} отклонён. Пожалуйста, свяжитесь с магазином.")
    except Exception:
        pass
