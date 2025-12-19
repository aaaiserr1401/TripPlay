import logging
import json
import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Переменная окружения BOT_TOKEN не задана")

ADMIN_ID_RAW = os.getenv("ADMIN_ID")
if not ADMIN_ID_RAW:
    raise RuntimeError("Переменная окружения ADMIN_ID не задана")
ADMIN_ID = int(ADMIN_ID_RAW)

# Номера телефонов для оплаты (замените на свои)
PAYMENT_PHONE_KASPI = "+7 747 048 5449"
PAYMENT_PHONE_HALYK = "+7 7470485449"

# Состояния разговора
(
    CHOOSING_DIRECTION,
    CHOOSING_TOUR_TYPE,
    CHOOSING_DATE,
    CONFIRMING_BOOKING,
    WAITING_RECEIPT,
    WAITING_ADMIN_CONFIRMATION
) = range(6)

# Направления туров
DIRECTIONS = {
    "charyn": "Чарынский каньон",
    "kolsai": "Кольсайские озёра",
    "altyn_emel": "Алтын-Эмель",
    "big_almaty": "Большое Алматинское озеро"
}

# Типы туров и их цены
TOUR_TYPES = {
    "interactive": {"name": "Интерактивный тур", "price": 60000},
    "photo": {"name": "Фототур", "price": 35000},
    "historical": {"name": "Исторический тур", "price": 30000},
    "regular": {"name": "Обычный тур", "price": 25000}
}

# Свободные даты (пример - можно расширить)
AVAILABLE_DATES = [
    "12 января",
    "19 января",
    "26 января",
    "2 февраля",
    "9 февраля",
    "16 февраля"
]

# Файл для хранения данных
DATA_FILE = os.path.join(os.path.dirname(__file__), "bookings.json")

def load_bookings():
    """Загружает данные о бронированиях из файла"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    return {}
                return json.loads(content)
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Ошибка чтения {DATA_FILE}: {e}")
            return {}
    return {}

def save_bookings(bookings):
    """Сохраняет данные о бронированиях в файл"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(bookings, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.error(f"Ошибка записи {DATA_FILE}: {e}")

def get_user_booking(user_id):
    """Получает текущее бронирование пользователя"""
    bookings = load_bookings()
    return bookings.get(str(user_id), {})

def save_user_booking(user_id, booking_data):
    """Сохраняет бронирование пользователя"""
    bookings = load_bookings()
    bookings[str(user_id)] = booking_data
    save_bookings(bookings)

def clear_user_booking(user_id):
    """Очищает бронирование пользователя"""
    bookings = load_bookings()
    if str(user_id) in bookings:
        del bookings[str(user_id)]
        save_bookings(bookings)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало работы с ботом - выбор направления"""
    user = update.effective_user
    
    # Очищаем предыдущее бронирование при новом старте
    clear_user_booking(user.id)
    
    keyboard = []
    for key, name in DIRECTIONS.items():
        keyboard.append([InlineKeyboardButton(name, callback_data=f"direction_{key}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message is not None:
        await update.message.reply_text(
            f"Добро пожаловать, {user.first_name}! 👋\n\n"
            "Я помогу вам забронировать тур. Пожалуйста, выберите направление:",
            reply_markup=reply_markup
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=(
                f"Добро пожаловать, {user.first_name}! 👋\n\n"
                "Я помогу вам забронировать тур. Пожалуйста, выберите направление:"
            ),
            reply_markup=reply_markup
        )
    
    return CHOOSING_DIRECTION

async def choose_direction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора направления"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("direction_"):
        direction_key = query.data.replace("direction_", "")
        direction_name = DIRECTIONS[direction_key]
        
        # Сохраняем выбор
        booking = get_user_booking(query.from_user.id)
        booking["direction"] = direction_key
        booking["direction_name"] = direction_name
        save_user_booking(query.from_user.id, booking)
        
        # Предлагаем выбрать тип тура
        keyboard = []
        for key, tour_info in TOUR_TYPES.items():
            keyboard.append([InlineKeyboardButton(
                f"{tour_info['name']} - {tour_info['price']:,} ₸",
                callback_data=f"tour_type_{key}"
            )])
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_direction")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"Отлично! Вы выбрали: *{direction_name}*\n\n"
            "Теперь выберите тип тура:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        return CHOOSING_TOUR_TYPE
    
    elif query.data == "back_to_direction":
        # Возврат к выбору направления
        keyboard = []
        for key, name in DIRECTIONS.items():
            keyboard.append([InlineKeyboardButton(name, callback_data=f"direction_{key}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Выберите направление:",
            reply_markup=reply_markup
        )
        
        return CHOOSING_DIRECTION

async def choose_tour_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора типа тура"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("tour_type_"):
        tour_type_key = query.data.replace("tour_type_", "")
        tour_info = TOUR_TYPES[tour_type_key]
        
        # Сохраняем выбор
        booking = get_user_booking(query.from_user.id)
        booking["tour_type"] = tour_type_key
        booking["tour_type_name"] = tour_info["name"]
        booking["price"] = tour_info["price"]
        save_user_booking(query.from_user.id, booking)
        
        # Предлагаем выбрать дату
        keyboard = []
        for date in AVAILABLE_DATES:
            keyboard.append([InlineKeyboardButton(date, callback_data=f"date_{date}")])
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_tour_type")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"Вы выбрали: *{tour_info['name']}*\n\n"
            "Выберите дату тура:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        return CHOOSING_DATE
    
    elif query.data == "back_to_tour_type":
        # Возврат к выбору типа тура
        booking = get_user_booking(query.from_user.id)
        direction_name = booking.get("direction_name", "")
        
        keyboard = []
        for key, tour_info in TOUR_TYPES.items():
            keyboard.append([InlineKeyboardButton(
                f"{tour_info['name']} - {tour_info['price']:,} ₸",
                callback_data=f"tour_type_{key}"
            )])
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_direction")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"Направление: *{direction_name}*\n\n"
            "Выберите тип тура:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        return CHOOSING_TOUR_TYPE

async def choose_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора даты"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("date_"):
        date = query.data.replace("date_", "")
        
        # Сохраняем выбор
        booking = get_user_booking(query.from_user.id)
        booking["date"] = date
        save_user_booking(query.from_user.id, booking)
        
        # Показываем итоговое подтверждение
        direction_name = booking.get("direction_name", "")
        tour_type_name = booking.get("tour_type_name", "")
        price = booking.get("price", 0)
        
        keyboard = [
            [InlineKeyboardButton("✅ Подтвердить бронь", callback_data="confirm_booking")],
            [InlineKeyboardButton("❌ Отменить бронь", callback_data="cancel_booking")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_to_date")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📋 *Итоговое подтверждение:*\n\n"
            f"📍 Направление: {direction_name}\n"
            f"🎯 Тип тура: {tour_type_name}\n"
            f"📅 Дата: {date}\n"
            f"💰 Цена: {price:,} ₸\n\n"
            "Подтвердите бронирование:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        return CONFIRMING_BOOKING
    
    elif query.data == "back_to_date":
        # Возврат к выбору даты
        booking = get_user_booking(query.from_user.id)
        tour_type_name = booking.get("tour_type_name", "")
        
        keyboard = []
        for date in AVAILABLE_DATES:
            keyboard.append([InlineKeyboardButton(date, callback_data=f"date_{date}")])
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_tour_type")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"Тип тура: *{tour_type_name}*\n\n"
            "Выберите дату тура:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        return CHOOSING_DATE

async def confirm_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка подтверждения или отмены брони"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_booking":
        booking = get_user_booking(query.from_user.id)
        booking["status"] = "waiting_payment"
        booking["created_at"] = datetime.now().isoformat()
        save_user_booking(query.from_user.id, booking)
        
        direction_name = booking.get("direction_name", "")
        tour_type_name = booking.get("tour_type_name", "")
        date = booking.get("date", "")
        price = booking.get("price", 0)
        
        await query.edit_message_text(
            "✅ *Бронирование подтверждено!*\n\n"
            "📱 *Реквизиты для оплаты:*\n\n"
            f"Kaspi: `{PAYMENT_PHONE_KASPI}`\n"
            f"Halyk: `{PAYMENT_PHONE_HALYK}`\n\n"
            f"💰 *Сумма к оплате: {price:,} ₸*\n\n"
            "📄 Пожалуйста, отправьте чек об оплате (фото или PDF файл).",
            parse_mode='Markdown'
        )
        
        return WAITING_RECEIPT
    
    elif query.data == "cancel_booking":
        clear_user_booking(query.from_user.id)
        
        await query.edit_message_text(
            "❌ Бронирование отменено.\n\n"
            "Все выбранные данные очищены.\n"
            "Вы можете начать заново, отправив /start"
        )
        
        return ConversationHandler.END
    
    elif query.data == "back_to_date":
        # Возврат к выбору даты
        booking = get_user_booking(query.from_user.id)
        tour_type_name = booking.get("tour_type_name", "")
        
        keyboard = []
        for date in AVAILABLE_DATES:
            keyboard.append([InlineKeyboardButton(date, callback_data=f"date_{date}")])
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_tour_type")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"Тип тура: *{tour_type_name}*\n\n"
            "Выберите дату тура:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        return CHOOSING_DATE

async def receive_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка получения чека"""
    user = update.effective_user
    booking = get_user_booking(user.id)
    
    # Проверяем, что это файл (фото или документ)
    if update.message.photo or (update.message.document and 
                                update.message.document.mime_type in ['application/pdf', 'image/jpeg', 'image/png']):
        
        # Сохраняем информацию о чеке
        booking["receipt_received"] = True
        booking["receipt_received_at"] = datetime.now().isoformat()
        booking["status"] = "waiting_admin_confirmation"
        
        if update.message.photo:
            booking["receipt_file_id"] = update.message.photo[-1].file_id
            booking["receipt_type"] = "photo"
        elif update.message.document:
            booking["receipt_file_id"] = update.message.document.file_id
            booking["receipt_type"] = "document"
        
        save_user_booking(user.id, booking)
        
        # Отправляем подтверждение пользователю
        await update.message.reply_text(
            "✅ Чек получен!\n\n"
            "⏳ Ожидайте подтверждения оплаты администратором."
        )
        
        # Отправляем уведомление администратору
        direction_name = booking.get("direction_name", "")
        tour_type_name = booking.get("tour_type_name", "")
        date = booking.get("date", "")
        price = booking.get("price", 0)
        username = user.username or "не указан"
        
        admin_message = (
            f"🔔 *Новая бронь ожидает подтверждения*\n\n"
            f"👤 Пользователь: @{username} (ID: {user.id})\n"
            f"📍 Направление: {direction_name}\n"
            f"🎯 Тип тура: {tour_type_name}\n"
            f"📅 Дата: {date}\n"
            f"💰 Сумма: {price:,} ₸\n\n"
            f"Используйте /confirm {user.id} для подтверждения"
        )
        
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_message,
                parse_mode='Markdown'
            )
            
            # Отправляем чек администратору
            if booking.get("receipt_type") == "photo":
                await context.bot.send_photo(
                    chat_id=ADMIN_ID,
                    photo=booking["receipt_file_id"],
                    caption=f"Чек от @{username}"
                )
            else:
                await context.bot.send_document(
                    chat_id=ADMIN_ID,
                    document=booking["receipt_file_id"],
                    caption=f"Чек от @{username}"
                )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления администратору: {e}")
        
        return WAITING_ADMIN_CONFIRMATION
    else:
        await update.message.reply_text(
            "❌ Пожалуйста, отправьте чек в виде фото или PDF файла."
        )
        return WAITING_RECEIPT

async def invalid_receipt_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Пожалуйста, отправьте чек в виде фото или PDF файла.")

async def waiting_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Ожидайте подтверждения оплаты администратором.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена бронирования в любой момент"""
    user = update.effective_user
    clear_user_booking(user.id)
    
    await update.message.reply_text(
        "❌ Бронирование отменено.\n\n"
        "Все выбранные данные очищены.\n"
        "Вы можете начать заново, отправив /start"
    )
    
    return ConversationHandler.END

async def admin_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение оплаты администратором"""
    if str(update.effective_user.id) != str(ADMIN_ID):
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return
    
    # Получаем ID пользователя из аргументов команды
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "Использование: /confirm <user_id>\n\n"
            "Или используйте команду из уведомления о новой брони."
        )
        return
    
    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Неверный формат ID пользователя.")
        return
    
    booking = get_user_booking(user_id)
    
    if not booking or booking.get("status") != "waiting_admin_confirmation":
        await update.message.reply_text("❌ Бронирование не найдено или уже обработано.")
        return
    
    # Обновляем статус
    booking["status"] = "confirmed"
    booking["confirmed_at"] = datetime.now().isoformat()
    save_user_booking(user_id, booking)
    
    # Отправляем подтверждение пользователю
    direction_name = booking.get("direction_name", "")
    tour_type_name = booking.get("tour_type_name", "")
    date = booking.get("date", "")
    price = booking.get("price", 0)
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "✅ *Оплата подтверждена!*\n\n"
                "🎉 *Тур забронирован*\n\n"
                f"📍 Направление: {direction_name}\n"
                f"🎯 Тип тура: {tour_type_name}\n"
                f"📅 Дата: {date}\n"
                f"💰 Сумма: {price:,} ₸\n\n"
                "ℹ️ За день до тура вам будет отправлена организационная информация."
            ),
            parse_mode='Markdown'
        )
        
        await update.message.reply_text("✅ Бронирование подтверждено! Пользователь уведомлен.")
    except Exception as e:
        logger.error(f"Ошибка отправки подтверждения пользователю: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def list_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список всех бронирований (только для администратора)"""
    if str(update.effective_user.id) != str(ADMIN_ID):
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return
    
    bookings = load_bookings()
    
    if not bookings:
        await update.message.reply_text("📭 Нет активных бронирований.")
        return
    
    message = "📋 *Список бронирований:*\n\n"
    
    for user_id, booking in bookings.items():
        status = booking.get("status", "unknown")
        direction = booking.get("direction_name", "не указано")
        date = booking.get("date", "не указана")
        price = booking.get("price", 0)
        
        status_emoji = {
            "waiting_payment": "⏳",
            "waiting_admin_confirmation": "🔔",
            "confirmed": "✅"
        }.get(status, "❓")
        
        message += (
            f"{status_emoji} ID: {user_id}\n"
            f"   {direction} - {date}\n"
            f"   {price:,} ₸ - {status}\n\n"
        )
    
    await update.message.reply_text(message, parse_mode='Markdown')

def main():
    """Запускает бота"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Создаем обработчик разговора
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING_DIRECTION: [CallbackQueryHandler(choose_direction)],
            CHOOSING_TOUR_TYPE: [CallbackQueryHandler(choose_tour_type)],
            CHOOSING_DATE: [CallbackQueryHandler(choose_date)],
            CONFIRMING_BOOKING: [CallbackQueryHandler(confirm_booking)],
            WAITING_RECEIPT: [
                MessageHandler(filters.PHOTO | filters.Document.ALL, receive_receipt),
                MessageHandler(filters.TEXT & ~filters.COMMAND, invalid_receipt_message)
            ],
            WAITING_ADMIN_CONFIRMATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, waiting_admin_message)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("confirm", admin_confirm))
    application.add_handler(CommandHandler("list", list_bookings))
    application.add_handler(CommandHandler("bookings", list_bookings))
    
    logger.info("Бот запущен...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
