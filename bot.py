import os
import logging
import asyncio
from typing import Dict, List
from uuid import uuid4
from datetime import datetime, timedelta
from dataclasses import dataclass

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BotCommand
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    Application
)

# --- Конфигурация --- #
class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    TIPS = [
        "✅ Завершить текущую задачу в дн",
        "📤 Отправить фидбек",
    ]
    TIMEZONE = "Europe/Moscow"

# --- Модели данных --- #
@dataclass
class Case:
    case_id: str
    user_id: int
    duration: int
    topic: str
    start_time: datetime
    end_time: datetime
    message_id: int = None
    is_completed: bool = False

    def time_left(self) -> str:
        delta = self.end_time - datetime.now()
        if delta.total_seconds() <= 0:
            return "⏰ Время вышло"
        minutes = delta.seconds // 60
        seconds = delta.seconds % 60
        return f"{minutes} мин {seconds} сек"

    def extend_time(self, minutes: int):
        self.end_time += timedelta(minutes=minutes)

# --- Хранилище данных --- #
class CaseManager:
    def __init__(self):
        self.active_cases: Dict[str, Case] = {}
        self.completed_cases: List[Case] = []

    def add_case(self, case: Case):
        self.active_cases[case.case_id] = case

    def complete_case(self, case_id: str):
        if case_id in self.active_cases:
            case = self.active_cases.pop(case_id)
            case.is_completed = True
            self.completed_cases.append(case)

# --- Основные обработчики --- #
class BotHandlers:
    def __init__(self, case_manager: CaseManager):
        self.case_manager = case_manager

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("➕ Новый кейс", callback_data="new_case")],
            [InlineKeyboardButton("📋 Мои кейсы", callback_data="show_cases"),
             InlineKeyboardButton("📊 Статистика", callback_data="stats")]
        ]
        await update.message.reply_text(
            "👋 Привет! Я помогу тебе управлять задачами.\n\n"
            "Используй /remindme чтобы создать напоминание",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def remindme(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if len(context.args) < 2:
                raise ValueError

            duration = int(context.args[0])
            topic = " ".join(context.args[1:])
            user_id = update.effective_user.id

            case = Case(
                case_id=str(uuid4())[:8],
                user_id=user_id,
                duration=duration,
                topic=topic,
                start_time=datetime.now(),
                end_time=datetime.now() + timedelta(minutes=duration)
            ) 
            self.case_manager.add_case(case)

            msg = await update.message.reply_text(
                f"✅ Кейс создан!\n"
                f"🆔 ID: {case.case_id}\n"
                f"📌 Тема: {topic}\n"
                f"⏰ Напоминание через: {duration} мин.\n"
                f"⏳ Окончание: {case.end_time.strftime('%H:%M')}"
            )
            case.message_id = msg.message_id

            asyncio.create_task(self._send_reminder(user_id, case.case_id, context))

        except (ValueError, IndexError):
            await update.message.reply_text(
                "⚠️ Неверный формат. Используй:\n"
                "/remindme <минуты> <описание задачи>\n"
                "Пример: /remindme 30 Проверить почту"
            )

    async def _send_reminder(self, user_id: int, case_id: str, context: ContextTypes.DEFAULT_TYPE):
        await asyncio.sleep(self.case_manager.active_cases[case_id].duration * 60)
        
        if case_id in self.case_manager.active_cases:
            case = self.case_manager.active_cases[case_id]
            await context.bot.send_message(
                chat_id=user_id,
                text=f"⏰ Время на кейс «{case.topic}» вышло!\n"
                     f"Используй /show_cases для управления"
            )
            self.case_manager.complete_case(case_id)

# --- Дополнительный функционал --- #
    async def show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        completed = len([c for c in self.case_manager.completed_cases if c.user_id == user_id])
        active = len([c for c in self.case_manager.active_cases.values() if c.user_id == user_id])
        
        await update.message.reply_text(
            f"📊 Ваша статистика:\n\n"
            f"✅ Завершено кейсов: {completed}\n"
            f"🔄 Активных задач: {active}\n"
            f"⏳ Среднее время выполнения: N/A"
        )

    async def show_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "📚 Справка по командам:\n\n"
            "/start - Главное меню\n"
            "/remindme <минуты> <задача> - Создать напоминание\n"
            "/show_cases - Активные задачи\n"
            "/stats - Ваша статистика\n"
            "/help - Эта справка\n\n"
            "ℹ️ Используй кнопки под сообщениями для быстрого управления"
        )
        await update.message.reply_text(help_text)

# --- Запуск бота --- #
async def set_bot_commands(application: Application):
    await application.bot.set_my_commands([
        BotCommand("start", "Главное меню"),
        BotCommand("remindme", "Создать напоминание"),
        BotCommand("show_cases", "Активные задачи"),
        BotCommand("stats", "Показать статистику"),
        BotCommand("help", "Помощь по командам")
    ])

def main():
    # Инициализация
    case_manager = CaseManager()
    handlers = BotHandlers(case_manager)

    # Настройка приложения
    app = ApplicationBuilder().token(Config.BOT_TOKEN).build()
    app.post_init = set_bot_commands

    # Регистрация обработчиков
    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("remindme", handlers.remindme))
    app.add_handler(CommandHandler("show_cases", handlers.show_cases))
    app.add_handler(CommandHandler("stats", handlers.show_stats))
    app.add_handler(CommandHandler("help", handlers.show_help))
    app.add_handler(CallbackQueryHandler(handlers.button_handler))

    # Запуск бота
    logging.info("Бот запущен и готов к работе!")
    app.run_polling()

if __name__ == "__main__":
    main()
