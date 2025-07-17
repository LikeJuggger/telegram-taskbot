import os
import json
import asyncio
import nest_asyncio
from datetime import time
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

# Щоби можна було запускати всередині вже працюючого лупа (Railway / Docker)
nest_asyncio.apply()

# Файл для збереження незакритих тем
THREAD_FILE = "threads.json"

# Стадії для ConversationHandler
NAME, DESCRIPTION, LINKS, ASSIGNEE, DEADLINE = range(5)
DONE_LINK = range(1)


# ----------------------------------------
# 🔧 Зберігання / Завантаження ID тем
# ----------------------------------------
def load_threads():
    if os.path.exists(THREAD_FILE):
        with open(THREAD_FILE, "r") as f:
            return json.load(f)
    return []


def save_threads(data):
    with open(THREAD_FILE, "w") as f:
        json.dump(data, f)


# ----------------------------------------
# 🤖 Команди бота
# ----------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! Напиши /newtask щоб створити нову задачу."
    )


# /newtask → початок збору даних
async def new_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["messages"] = [update.message.message_id]
    await update.message.reply_text("📌 Назва задачі?")
    return NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text
    context.user_data["messages"].append(update.message.message_id)
    await update.message.reply_text("📝 Опиши суть задачі:")
    return DESCRIPTION


async def get_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["description"] = update.message.text
    context.user_data["messages"].append(update.message.message_id)
    await update.message.reply_text("📎 Додай посилання або напиши «немає»")
    return LINKS


async def get_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["links"] = update.message.text
    context.user_data["messages"].append(update.message.message_id)
    await update.message.reply_text("👤 Хто виконавець? Вкажи @username:")
    return ASSIGNEE


async def get_assignee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["assignee"] = update.message.text
    context.user_data["messages"].append(update.message.message_id)
    await update.message.reply_text("⏰ Який дедлайн?")
    return DEADLINE


# Після DEADLINE — створюємо тему, зберігаємо ID, відправляємо самарі, пінемо, очищуємо
async def get_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["deadline"] = update.message.text
    context.user_data["messages"].append(update.message.message_id)
    data = context.user_data

    summary = (
        f"✅ *Нова задача!*\n\n"
        f"*Назва:* {data['name']}\n"
        f"*Опис:* {data['description']}\n"
        f"*Матеріали:* {data['links']}\n"
        f"*Виконавець:* {data['assignee']}\n"
        f"*Дедлайн:* {data['deadline']}"
    )

    # Створюємо гілку з червоним кружечком
    topic = await context.bot.create_forum_topic(
        chat_id=update.effective_chat.id,
        name=f"🔴 {data['name']} – {data['assignee']}"
    )

    # Зберігаємо актуальну ID гілки
    threads = load_threads()
    threads.append(topic.message_thread_id)
    save_threads(threads)

    # Відправляємо самарі в ту гілку
    msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        message_thread_id=topic.message_thread_id,
        text=summary,
        parse_mode="Markdown"
    )

    # Закріплюємо повідомлення
    await context.bot.pin_chat_message(
        chat_id=update.effective_chat.id,
        message_id=msg.message_id
    )

    # Видаляємо питання бота
    for msg_id in data.get("messages", []):
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=msg_id
            )
        except:
            pass

    context.user_data.clear()
    return ConversationHandler.END


# /cancel — в будь-який момент
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Задачу скасовано.")
    return ConversationHandler.END


# ----------------------------------------
# ✅ Завершення задачі (/done)
# ----------------------------------------
async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔗 Додай посилання на результат:")
    return DONE_LINK


async def done_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result_link = update.message.text
    thread_id = update.message.message_thread_id
    chat_id = update.effective_chat.id

    # Перейменовуємо тему з 🔴 → 🟢
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

    # Прибираємо з файлу закритих
    try:
        threads = load_threads()
        threads = [tid for tid in threads if tid != thread_id]
        save_threads(threads)
    except Exception as e:
        print(f"[Remove Error] {e}")

    await update.message.reply_text(
        f"✅ Задачу завершено!\nПосилання: {result_link}"
    )
    return ConversationHandler.END


# ----------------------------------------
# 🔔 Нагадування про незакриті
# ----------------------------------------
async def send_reminders(bot):
    # ID групи (заміні на свій!)
    chat_id = -1001234567890
    threads = load_threads()

    for thread_id in threads:
        try:
            await bot.send_message(
                chat_id=chat_id,
                message_thread_id=thread_id,
                text="🔔 Нагадування: задача ще не закрита!"
            )
        except Exception as e:
            print(f"[Reminder Error] {e}")


# ----------------------------------------
# 🔁 Основна функція
# ----------------------------------------
async def main():
    TOKEN = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("newtask", new_task),
            CommandHandler("done", done),
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
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)

    # Заплануємо щоденний ранковий рімайндер о 06:00 UTC (≈09:00 Київ)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_reminders,
        trigger="cron",
        hour=6,
        minute=0,
        args=[app.bot]
    )
    scheduler.start()

    print("🤖 Бот запущено!")
    await app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
