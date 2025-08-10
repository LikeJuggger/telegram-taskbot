import os
import json
import asyncio
from datetime import datetime, date, time as dtime
from zoneinfo import ZoneInfo
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

THREAD_FILE = "threads.json"
REMIND_FILE = "reminders.json"
TZ = ZoneInfo("Europe/Kyiv")

NAME, DESCRIPTION, LINKS, ASSIGNEE, DEADLINE, BACK = range(6)
REM_TARGET, REM_TITLE, REM_TEXT, REM_TYPE, REM_TIME, REM_START, REM_END = range(6, 13)
DONE_LINK = 20

MAIN_KB = ReplyKeyboardMarkup([
    [KeyboardButton("➕ Створити задачу"), KeyboardButton("⏰ Створити нагадування")],
    [KeyboardButton("✅ Закрити задачу"), KeyboardButton("🛑 Вимкнути нагадування")]
], resize_keyboard=True)

def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try: return json.load(f)
            except: return []
    return []

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def find_thread(chat_id, thread_id):
    for t in load_json(THREAD_FILE):
        if t["chat_id"] == chat_id and t["id"] == thread_id:
            return t
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Вітаю! Оберіть дію:", reply_markup=MAIN_KB)

async def new_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["step"] = NAME
    await update.message.reply_text("📌 Назва задачі?", reply_markup=ReplyKeyboardMarkup([["⬅️ Назад"]], resize_keyboard=True))
    return NAME

async def back_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("step")
    if step == DESCRIPTION:
        await update.message.reply_text("📌 Назва задачі?")
        context.user_data["step"] = NAME
        return NAME
    elif step == LINKS:
        await update.message.reply_text("📝 Опиши суть задачі:")
        context.user_data["step"] = DESCRIPTION
        return DESCRIPTION
    elif step == ASSIGNEE:
        await update.message.reply_text("📌 Додай посилання або напиши «немає»")
        context.user_data["step"] = LINKS
        return LINKS
    elif step == DEADLINE:
        await update.message.reply_text("👤 Хто виконавець? Вкажи @username:")
        context.user_data["step"] = ASSIGNEE
        return ASSIGNEE
    return NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад": return await back_step(update, context)
    context.user_data["name"] = update.message.text
    context.user_data["step"] = DESCRIPTION
    await update.message.reply_text("📝 Опиши суть задачі:")
    return DESCRIPTION

async def get_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад": return await back_step(update, context)
    context.user_data["description"] = update.message.text
    context.user_data["step"] = LINKS
    await update.message.reply_text("📌 Додай посилання або напиши «немає»")
    return LINKS

async def get_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад": return await back_step(update, context)
    context.user_data["links"] = update.message.text
    context.user_data["step"] = ASSIGNEE
    await update.message.reply_text("👤 Хто виконавець? Вкажи @username:")
    return ASSIGNEE

async def get_assignee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад": return await back_step(update, context)
    context.user_data["assignee"] = update.message.text
    context.user_data["step"] = DEADLINE
    await update.message.reply_text("⏰ Який дедлайн? (формат YYYY-MM-DD або «немає»)")
    return DEADLINE

async def get_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад": return await back_step(update, context)
    context.user_data["deadline"] = update.message.text
    data = context.user_data
    base_name = f"{data['name']} – {data['assignee']}"
    topic = await context.bot.create_forum_topic(
        chat_id=update.effective_chat.id,
        name=f"🔴 {base_name}"
    )
    threads = load_json(THREAD_FILE)
    threads.append({
        "id": topic.message_thread_id,
        "chat_id": update.effective_chat.id,
        "base_name": base_name
    })
    save_json(THREAD_FILE, threads)
    summary = (
        f"<b>Нова задача!</b>\n\n"
        f"<b>Назва:</b> {data['name']}\n"
        f"<b>Опис:</b> {data['description']}\n"
        f"<b>Матеріали:</b> {data['links']}\n"
        f"<b>Виконавець:</b> {data['assignee']}\n"
        f"<b>Дедлайн:</b> {data['deadline']}"
    )
    msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        message_thread_id=topic.message_thread_id,
        text=summary,
        parse_mode="HTML"
    )
    await context.bot.pin_chat_message(
        chat_id=update.effective_chat.id,
        message_id=msg.message_id
    )
    await update.message.reply_text("✅ Задачу створено!", reply_markup=MAIN_KB)
    return ConversationHandler.END

### >>> КІНЕЦЬ ЧАСТИНИ 1 <<<
### >>> ПОЧАТОК ЧАСТИНИ 2 <<<

async def scheduler_job(bot):
    now = datetime.now(TZ)
    rems = load_json(REMIND_FILE)
    for r in rems:
        if r["type"] == "Одноразове":
            pass
        elif r["type"] == "Щоденне з датами":
            sd = datetime.strptime(r["start_date"], "%Y-%m-%d").date()
            ed = datetime.strptime(r["end_date"], "%Y-%m-%d").date()
            if sd <= now.date() <= ed and now.strftime("%H:%M") == r["time"]:
                await bot.send_message(chat_id=r["chat_id"], text=r["text"])
        elif r["type"] == "Щоденне без кінцевої дати":
            if now.strftime("%H:%M") == r["time"]:
                await bot.send_message(chat_id=r["chat_id"], text=r["text"])

TOKEN = os.getenv("BOT_TOKEN")
app = ApplicationBuilder().token(TOKEN).build()

conv_task = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^➕ Створити задачу$"), new_task)],
    states={
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
        DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_description)],
        LINKS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_links)],
        ASSIGNEE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_assignee)],
        DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_deadline)],
    },
    fallbacks=[],
)

conv_rem = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^⏰ Створити нагадування$"), rem_target)],
    states={
        REM_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, rem_title)],
        REM_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, rem_text)],
        REM_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, rem_type)],
        REM_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, rem_start)],
        REM_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, rem_end)],
        REM_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, rem_time)],
    },
    fallbacks=[],
)

app.add_handler(CommandHandler("start", start))
app.add_handler(conv_task)
app.add_handler(conv_rem)
app.add_handler(MessageHandler(filters.Regex("^✅ Закрити задачу$"), close_task))
app.add_handler(MessageHandler(filters.Regex("^🛑 Вимкнути нагадування$"), disable_reminders))
app.add_handler(MessageHandler(filters.ALL, remove_reminder))

scheduler = AsyncIOScheduler(timezone=TZ)
scheduler.add_job(lambda: asyncio.create_task(scheduler_job(app.bot)), "cron", minute="*")
scheduler.start()

if __name__ == "__main__":
    print("🤖 Бот запущено!")
    app.run_polling()
