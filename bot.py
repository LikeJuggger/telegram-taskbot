from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import time
import os

# Стадії
NAME, DESCRIPTION, LINKS, ASSIGNEE, DEADLINE = range(5)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"[DEBUG] Chat ID: {update.effective_chat.id}")
    await update.message.reply_text("Привіт! Напиши /newtask щоб створити нову задачу.")

# Початок
async def new_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['messages'] = [update.message.message_id]
    await update.message.reply_text("📌 Назва задачі?")
    return NAME

# Збір даних + зберігання ID повідомлень
async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    context.user_data['messages'].append(update.message.message_id)
    await update.message.reply_text("📝 Опиши суть задачі:")
    return DESCRIPTION

async def get_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['description'] = update.message.text
    context.user_data['messages'].append(update.message.message_id)
    await update.message.reply_text("📎 Додай посилання або напиши «немає»")
    return LINKS

async def get_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['links'] = update.message.text
    context.user_data['messages'].append(update.message.message_id)
    await update.message.reply_text("👤 Хто виконавець? Вкажи @username:")
    return ASSIGNEE

async def get_assignee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['assignee'] = update.message.text
    context.user_data['messages'].append(update.message.message_id)
    await update.message.reply_text("⏰ Який дедлайн?")
    return DEADLINE

# Завершення
async def get_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['deadline'] = update.message.text
    context.user_data['messages'].append(update.message.message_id)

    data = context.user_data
    summary = (
        f"✅ *Нова задача!*\n\n"
        f"*Назва:* {data['name']}\n"
        f"*Опис:* {data['description']}\n"
        f"*Матеріали:* {data['links']}\n"
        f"*Виконавець:* {data['assignee']}\n"
        f"*Дедлайн:* {data['deadline']}"
    )

    topic_title = f"🔴 {data['name']} – {data['assignee']}"
    topic = await context.bot.create_forum_topic(
        chat_id=update.effective_chat.id,
        name=topic_title
    )

    msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        message_thread_id=topic.message_thread_id,
        text=summary,
        parse_mode="Markdown"
    )

    await context.bot.pin_chat_message(
        chat_id=update.effective_chat.id,
        message_id=msg.message_id
    )

    # Очистка тимчасових даних
    for msg_id in data.get("messages", []):
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
        except:
            pass

    context.user_data.clear()
    context.conversation_data.clear()
    return ConversationHandler.END

# Скасування
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Задачу скасовано.")
    return ConversationHandler.END

# 🕒 Функція нагадування
async def send_reminders(bot):
    chat_id = -1001234567890  # Замінити на ID твоєї групи
    try:
        topics = await bot.get_forum_topic_list(chat_id=chat_id)
        for topic in topics:
            if "🔴" in topic.name:
                await bot.send_message(
                    chat_id=chat_id,
                    message_thread_id=topic.message_thread_id,
                    text="🔔 Нагадування: задача ще не закрита!"
                )
    except Exception as e:
        print(f"[Reminder Error] {e}")

# 🚀 Запуск
if __name__ == '__main__':
    TOKEN = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()

    # Планувальник
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_reminders, trigger='cron', hour=23, minute=20, args=[app.bot])
    scheduler.start()

    # Хендлери
    conv = ConversationHandler(
        entry_points=[CommandHandler("newtask", new_task)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_description)],
            LINKS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_links)],
            ASSIGNEE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_assignee)],
            DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_deadline)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=False
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)

    print("🤖 Бот запущено!")
    app.run_polling()
