import os
import json
import asyncio
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
import nest_asyncio

# Файл для збереження thread_id всіх незакритих задач
THREAD_FILE = "threads.json"

# —————————————————————————
# СТАНИ ДЛЯ CONVERSATIONHANDLER
# —————————————————————————
NAME, DESCRIPTION, LINKS, ASSIGNEE, DEADLINE, DONE_LINK = range(6)

# —————————————————————————
# Завантаження / збереження списку тем
# —————————————————————————
def load_threads():
    if os.path.exists(THREAD_FILE):
        with open(THREAD_FILE, "r") as f:
            return json.load(f)
    return []

def save_threads(data):
    with open(THREAD_FILE, "w") as f:
        json.dump(data, f)

# —————————————————————————
# КОМАНДА /start
# —————————————————————————
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! /newtask — створити задачу.\n"
        "/done — закрити поточну (у темі)."
    )

# —————————————————————————
# СТВОРЕННЯ НОВОЇ ЗАДАЧІ
# —————————————————————————
async def new_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data['messages'] = [update.message.message_id]
    await update.message.reply_text("📌 Назва задачі?")
    return NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    context.user_data['messages'].append(update.message.message_id)
    await update.message.reply_text("📝 Опис задачі:")
    return DESCRIPTION

async def get_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['description'] = update.message.text
    context.user_data['messages'].append(update.message.message_id)
    await update.message.reply_text("📎 Посилання або «немає»")
    return LINKS

async def get_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['links'] = update.message.text
    context.user_data['messages'].append(update.message.message_id)
    await update.message.reply_text("👤 Виконавець (@username):")
    return ASSIGNEE

async def get_assignee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['assignee'] = update.message.text
    context.user_data['messages'].append(update.message.message_id)
    await update.message.reply_text("⏰ Дедлайн (будь-який формат):")
    return DEADLINE

async def get_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Спочатку зберігаємо дедлайн
    context.user_data['deadline'] = update.message.text
    context.user_data['messages'].append(update.message.message_id)

    data = context.user_data
    # Формуємо текст
    summary = (
        f"✅ *Нова задача!*\n\n"
        f"*Назва:* {data['name']}\n"
        f"*Опис:* {data['description']}\n"
        f"*Матеріали:* {data['links']}\n"
        f"*Виконавець:* {data['assignee']}\n"
        f"*Дедлайн:* {data['deadline']}"
    )

    # Спробуємо створити тему
    topic = None
    try:
        topic = await context.bot.create_forum_topic(
            chat_id=update.effective_chat.id,
            name=f"🔴 {data['name']} — {data['assignee']}"
        )
        # збережемо її єдиний ID для нагадувань
        threads = load_threads()
        threads.append(topic.message_thread_id)
        save_threads(threads)
    except Exception as e:
        print(f"[Topic Error] {e}")

    # Куди відправляти summary?
    if topic:
        dest = dict(
            chat_id=update.effective_chat.id,
            message_thread_id=topic.message_thread_id
        )
    else:
        dest = dict(chat_id=update.effective_chat.id)

    msg = await context.bot.send_message(
        **dest,
        text=summary,
        parse_mode="Markdown"
    )

    # А тепер закріпимо (якщо тема є)
    if topic:
        try:
            await context.bot.pin_chat_message(
                chat_id=update.effective_chat.id,
                message_id=msg.message_id
            )
        except Exception as e:
            print(f"[Pin Error] {e}")

    # Видаляємо проміжні питання
    for m in data.get("messages", []):
        try:
            await context.bot.delete_message(update.effective_chat.id, m)
        except:
            pass

    context.user_data.clear()
    return ConversationHandler.END

# —————————————————————————
# СКАСУВАННЯ
# —————————————————————————
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Скасовано.")
    context.user_data.clear()
    return ConversationHandler.END

# —————————————————————————
# ЗАВЕРШЕННЯ ЗАДАЧІ (/done)
# —————————————————————————
async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔗 Кидай тут лінк на результат:")
    return DONE_LINK

async def done_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result_link = update.message.text
    thread_id = update.message.message_thread_id
    chat_id = update.effective_chat.id

    # Перейменовуємо тему на 🟢
    try:
        topic = await context.bot.get_forum_topic(
            chat_id=chat_id,
            message_thread_id=thread_id
        )
        new_name = topic.name.replace("🔴", "🟢", 1)
        await context.bot.edit_forum_topic(
            chat_id=chat_id,
            message_thread_id=thread_id,
            name=new_name
        )
    except Exception as e:
        print(f"[Edit Error] {e}")

    # Видалимо з наших "threads.json"
    try:
        threads = load_threads()
        threads = [tid for tid in threads if tid != thread_id]
        save_threads(threads)
    except Exception as e:
        print(f"[Remove Error] {e}")

    await update.message.reply_text(
        f"✅ Задача завершена!\nПосилання: {result_link}"
    )
    return ConversationHandler.END

# —————————————————————————
# НАГАДУВАННЯ
# —————————————————————————
async def send_reminders(bot):
    chat_id = -1002737596438  # → заміни на свій Chat ID (Debug: print його через /start)
    threads = load_threads()
    for tid in threads:
        try:
            await bot.send_message(
                chat_id=chat_id,
                message_thread_id=tid,
                text="🔔 Нагадування: задача ще не закрита!"
            )
        except Exception as e:
            print(f"[Reminder Error] {e}")

# —————————————————————————
# MAIN
# —————————————————————————
async def main():
    nest_asyncio.apply()
    TOKEN = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("newtask", new_task),
            CommandHandler("done", done)
        ],
        states={
            NAME:       [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            DESCRIPTION:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_description)],
            LINKS:      [MessageHandler(filters.TEXT & ~filters.COMMAND, get_links)],
            ASSIGNEE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, get_assignee)],
            DEADLINE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, get_deadline)],
            DONE_LINK:  [MessageHandler(filters.TEXT & ~filters.COMMAND, done_link)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=False
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)

    scheduler = AsyncIOScheduler()
    # Нагадування щоранку о 06:00 (UTC+3 → локально 09:00)
    scheduler.add_job(send_reminders, trigger='cron', hour=6, minute=0, args=[app.bot])
    scheduler.start()

    print("🤖 Бот запущено!")
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
