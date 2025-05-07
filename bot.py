import os
import logging
import asyncio
from uuid import uuid4
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Получаем токен из переменной окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Подсказки
TIPS = [
    "✅ Завершить задачу в дн",
    "📤 Отправить фидбек",
]

# Хранилище активных кейсов
active_cases = {}

# Класс кейса
class Case:
    def __init__(self, user_id, duration, topic):
        self.case_id = str(uuid4())[:8]
        self.user_id = user_id
        self.duration = duration
        self.topic = topic
        self.start_time = datetime.now()
        self.end_time = self.start_time + timedelta(minutes=duration)
        self.message_id = None

    def time_left(self):
        delta = self.end_time - datetime.now()
        if delta.total_seconds() <= 0:
            return "⏰ Время вышло"
        minutes = delta.seconds // 60
        seconds = delta.seconds % 60
        return f"{minutes} мин {seconds} сек"

    def extend_time(self, minutes):
        self.end_time += timedelta(minutes=minutes)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("➕ Новый кейс", callback_data="new_case")],
        [InlineKeyboardButton("📋 Показать кейсы", callback_data="show_cases")]
    ]
    await update.message.reply_text(
        "👋 Привет! Я бот для управления кейсами.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Команда /remindme <минут> <тема>
async def remindme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        duration = int(context.args[0])
        topic = " ".join(context.args[1:])
        user_id = update.effective_user.id

        case = Case(user_id, duration, topic)
        active_cases[case.case_id] = case

        msg = await update.message.reply_text(
            f"✅ Кейс создан!\n🆔 {case.case_id}\n📌 {topic}\n⏰ Напомню через {duration} минут."
        )
        case.message_id = msg.message_id

        asyncio.create_task(remind_later(user_id, case.case_id, duration, topic, context))

    except Exception:
        await update.message.reply_text("⚠️ Ошибка. Используй: /remindme 10 Тема кейса")

# Асинхронное напоминание
async def remind_later(user_id, case_id, duration, topic, context):
    case = active_cases.get(case_id)

    if duration > 1:
        await asyncio.sleep((duration - 1) * 60)
        if case_id in active_cases:
            await context.bot.send_message(chat_id=user_id, text=f"⚠️ Осталась 1 минута на кейс «{topic}»!")

    await asyncio.sleep(60)
    if case_id in active_cases:
        await context.bot.send_message(chat_id=user_id, text=f"⏰ Время на кейс «{topic}» вышло!")
        del active_cases[case_id]

# Показывает все активные кейсы пользователя
async def show_cases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_cases = [c for c in active_cases.values() if c.user_id == user_id]

    if not user_cases:
        await (update.message or update.callback_query.message).reply_text("🗂 У тебя нет активных кейсов.")
        return

    for c in user_cases:
        keyboard = [
            [
                InlineKeyboardButton("❌ Удалить", callback_data=f"delete_{c.case_id}"),
                InlineKeyboardButton("➕ 5 мин", callback_data=f"extend_{c.case_id}"),
                InlineKeyboardButton("ℹ️ Подсказка", callback_data=f"tip_{c.case_id}")
            ]
        ]
        text = f"🆔 {c.case_id}\n📌 {c.topic}\n⏱ Осталось: {c.time_left()}"
        msg = await context.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        c.message_id = msg.message_id

# Обработка нажатий на кнопки
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data == "new_case":
        await query.message.reply_text("✍️ Отправь сообщение:\n/remindme 10 Проверка отчета")
    elif data == "show_cases":
        await show_cases(update, context)
    elif data.startswith("delete_"):
        case_id = data.split("_")[1]
        case = active_cases.get(case_id)
        if case and case.user_id == user_id:
            del active_cases[case_id]
            await query.message.reply_text(f"🗑 Кейс «{case.topic}» удалён.")
    elif data.startswith("extend_"):
        case_id = data.split("_")[1]
        case = active_cases.get(case_id)
        if case and case.user_id == user_id:
            case.extend_time(5)
            text = f"🆔 {case.case_id}\n📌 {case.topic}\n⏱ Осталось: {case.time_left()}"
            keyboard = [
                [
                    InlineKeyboardButton("❌ Удалить", callback_data=f"delete_{case.case_id}"),
                    InlineKeyboardButton("➕ 5 мин", callback_data=f"extend_{case.case_id}"),
                    InlineKeyboardButton("ℹ️ Подсказка", callback_data=f"tip_{case.case_id}")
                ]
            ]
            await context.bot.edit_message_text(
                chat_id=user_id,
                message_id=case.message_id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await query.message.reply_text(f"⏱ Время продлено на 5 минут.")
    elif data.startswith("tip_"):
        tip = TIPS[datetime.now().second % len(TIPS)]
        await query.message.reply_text(f"💡 Подсказка: {tip}")

# Запуск бота
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("remindme", remindme))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("✅ Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
