import logging
import json
import os
from datetime import time

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TOKEN = "YOUR_BOT_TOKEN_HERE"  # ← Замінити на свій токен
TASKS_FILE = "tasks.json"

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)

# ========== Зберігання задач ==========

def load_tasks():
    if os.path.exists(TASKS_FILE):
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_tasks():
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2, ensure_ascii=False)

tasks = load_tasks()

# ========== Команди ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Бот запущено!")

async def newtask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    title = " ".join(context.args) if context.args else "Нова задача"
    thread_name = f"🔴 {title}"

    forum_msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        message_thread_id=None,
        text=f"🧵 Тема: {title}",
        message_thread_name=thread_name,
    )

    summary = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        message_thread_id=forum_msg.message_thread_id,
        text=f"📌 Задача: {title}\nНатисни /done коли завершиш.",
    )

    await context.bot.pin_chat_message(
        chat_id=update.effective_chat.id,
        message_id=summary.message_id,
        message_thread_id=forum_msg.message_thread_id,
        disable_notification=True,
    )

    tasks[str(forum_msg.message_thread_id)] = {
        "chat_id": update.effective_chat.id,
        "thread_name": thread_name,
        "status": "active",
    }
    save_tasks()

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.is_topic_message:
        await update.message.reply_text("⚠️ Цю команду потрібно запускати в гілці задачі.")
        return

    thread_id = str(update.message.message_thread_id)
    task = tasks.get(thread_id)

    if not task or task["status"] == "done":
        await update.message.reply_text("✅ Ця задача вже завершена або не знайдена.")
        return

    new_name = task["thread_name"].replace("🔴", "🟢", 1)

    try:
        await context.bot.edit_forum_topic(
            chat_id=task["chat_id"],
            message_thread_id=int(thread_id),
            name=new_name
        )
        task["status"] = "done"
        task["thread_name"] = new_name
        save_tasks()
        await update.message.reply_text("🟢 Задача позначена як виконана!")
    except Exception as e:
        logging.error(f"❌ Помилка при оновленні назви теми: {e}")
        await update.message.reply_text("⚠️ Не вдалося оновити тему. Але задача збережена як завершена.")
        task["status"] = "done"
        save_tasks()

# ========== Нагадування ==========

async def send_reminders(context: ContextTypes.DEFAULT_TYPE):
    for thread_id, task in tasks.items():
        if task["status"] != "active":
            continue
        try:
            await context.bot.send_message(
                chat_id=task["chat_id"],
                message_thread_id=int(thread_id),
                text="⏰ Нагадування: задача все ще активна. Не забудь натиснути /done!",
            )
        except Exception as e:
            logging.warning(f"⚠️ Не вдалося надіслати нагадування в гілку {thread_id}: {e}")

# ========== Основна логіка ==========

async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Планувальник
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_reminders,
        trigger="cron",
        hour=23,
        minute=20,
        args=[app.bot],
    )
    scheduler.start()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newtask", newtask))
    app.add_handler(CommandHandler("done", done))

    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
