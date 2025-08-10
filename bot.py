import os, json, asyncio, uuid, re
from datetime import datetime, date, time as dtime, timedelta
from zoneinfo import ZoneInfo
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ConversationHandler, ContextTypes, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TZ = ZoneInfo("Europe/Kyiv")
THREAD_FILE = "threads.json"
REMIND_FILE = "reminders.json"

NAME, DESCRIPTION, LINKS, ASSIGNEE, DEADLINE = range(5)
RTARGET, RSELECT_THREAD, RTITLE, RTEXT, RTYPE, RSTART, REND, RTIME = range(10, 18)

MAIN_KB = ReplyKeyboardMarkup(
    [[KeyboardButton("➕ Створити задачу"), KeyboardButton("⏰ Створити нагадування")],
     [KeyboardButton("✅ Закрити задачу"), KeyboardButton("🛑 Вимкнути нагадування")]],
    resize_keyboard=True
)

def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try: return json.load(f)
            except: return []
    return []

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def list_open_threads():
    return load_json(THREAD_FILE)

def upsert_thread(rec):
    data = load_json(THREAD_FILE)
    data.append(rec)
    save_json(THREAD_FILE, data)

def remove_thread(chat_id, thread_id):
    data = load_json(THREAD_FILE)
    data = [t for t in data if not (t["chat_id"] == chat_id and t["id"] == thread_id)]
    save_json(THREAD_FILE, data)

def find_thread(chat_id, thread_id):
    for t in load_json(THREAD_FILE):
        if t["chat_id"] == chat_id and t["id"] == thread_id:
            return t
    return None

def upsert_reminder(rem):
    data = load_json(REMIND_FILE)
    data = [r for r in data if r.get("id") != rem["id"]]
    data.append(rem)
    save_json(REMIND_FILE, data)

def get_reminders(active_only=True):
    data = load_json(REMIND_FILE)
    if active_only:
        data = [r for r in data if r.get("active", True)]
    return data

def deactivate_reminder_by_title(title):
    data = load_json(REMIND_FILE)
    changed = False
    for r in data:
        if r.get("title") == title and r.get("active", True):
            r["active"] = False
            r["job_ids"] = []
            changed = True
    if changed: save_json(REMIND_FILE, data)
    return changed

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
    await update.message.reply_text("⏰ Який дедлайн? (YYYY-MM-DD або «немає»)")
    return DEADLINE

async def get_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад": return await back_step(update, context)
    context.user_data["deadline"] = update.message.text
    data = context.user_data
    base_name = f"{data['name']} – {data['assignee']}"
    topic = await context.bot.create_forum_topic(chat_id=update.effective_chat.id, name=f"🔴 {base_name}")
    upsert_thread({"id": topic.message_thread_id, "chat_id": update.effective_chat.id, "base_name": base_name})
    summary = (f"<b>Нова задача!</b>\n\n"
               f"<b>Назва:</b> {data['name']}\n"
               f"<b>Опис:</b> {data['description']}\n"
               f"<b>Матеріали:</b> {data['links']}\n"
               f"<b>Виконавець:</b> {data['assignee']}\n"
               f"<b>Дедлайн:</b> {data['deadline']}")
    msg = await context.bot.send_message(chat_id=update.effective_chat.id, message_thread_id=topic.message_thread_id, text=summary, parse_mode="HTML")
    await context.bot.pin_chat_message(chat_id=update.effective_chat.id, message_id=msg.message_id)
    await update.message.reply_text("✅ Задачу створено!", reply_markup=MAIN_KB)
    return ConversationHandler.END

async def close_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    thread_id = update.message.message_thread_id
    chat_id = update.effective_chat.id
    if thread_id is None:
        await update.message.reply_text("❌ Це не тема задачі.", reply_markup=MAIN_KB); return
    rec = find_thread(chat_id, thread_id)
    if not rec:
        await update.message.reply_text("❌ Ця тема не зареєстрована як задача.", reply_markup=MAIN_KB); return
    new_name = f"🟢 {rec['base_name']}"
    await context.bot.edit_forum_topic(chat_id=chat_id, message_thread_id=thread_id, name=new_name)
    remove_thread(chat_id, thread_id)
    await update.message.reply_text("✅ Задачу закрито.", reply_markup=MAIN_KB)

async def rem_start_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    kb = ReplyKeyboardMarkup([["Для всіх відкритих задач"], ["У конкретну гілку"], ["Скасувати"]], resize_keyboard=True)
    await update.message.reply_text("Куди надіслати нагадування?", reply_markup=kb)
    return RTARGET

async def rem_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text
    if txt == "Скасувати":
        await update.message.reply_text("Скасовано.", reply_markup=MAIN_KB); return ConversationHandler.END
    if txt == "Для всіх відкритих задач":
        context.user_data["target"] = {"mode":"all_open"}
        await update.message.reply_text("Введіть коротку назву нагадування:", reply_markup=ReplyKeyboardMarkup([["Скасувати"]], resize_keyboard=True))
        return RTITLE
    context.user_data["target"] = {"mode":"specific"}
    threads = list_open_threads()
    rows = [[f"{t['base_name']} (id:{t['id']})"] for t in threads] + [["General (id:general)"], ["Скасувати"]]
    await update.message.reply_text("Оберіть гілку:", reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True))
    return RSELECT_THREAD

async def rem_select_thread(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text
    if txt == "Скасувати":
        await update.message.reply_text("Скасовано.", reply_markup=MAIN_KB); return ConversationHandler.END
    m = re.search(r"id:(\d+|general)", txt)
    if not m:
        await update.message.reply_text("Не зміг визначити id. Спробуйте знову або введіть у форматі id:12345.")
        return RSELECT_THREAD
    tid = m.group(1)
    thread_id = None if tid == "general" else int(tid)
    context.user_data["target"]["thread_id"] = thread_id
    await update.message.reply_text("Введіть коротку назву нагадування:", reply_markup=ReplyKeyboardMarkup([["Скасувати"]], resize_keyboard=True))
    return RTITLE

async def rem_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "Скасувати":
        await update.message.reply_text("Скасовано.", reply_markup=MAIN_KB); return ConversationHandler.END
    context.user_data["title"] = update.message.text.strip()
    await update.message.reply_text("Введіть текст нагадування:")
    return RTEXT

async def rem_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["text"] = update.message.text
    kb = ReplyKeyboardMarkup([["Одноразове"], ["Щоденне з датами"], ["Щоденне без кінцевої дати"], ["Скасувати"]], resize_keyboard=True)
    await update.message.reply_text("Оберіть тип:", reply_markup=kb)
    return RTYPE

async def rem_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text
    if t == "Скасувати":
        await update.message.reply_text("Скасовано.", reply_markup=MAIN_KB); return ConversationHandler.END
    context.user_data["rtype"] = t
    if t == "Одноразове":
        await update.message.reply_text("Час: HH:MM сьогодні або у форматі +N (хвилин).", reply_markup=ReplyKeyboardMarkup([["Скасувати"]], resize_keyboard=True))
        return RTIME
    if t == "Щоденне з датами":
        await update.message.reply_text("Дата початку (YYYY-MM-DD):", reply_markup=ReplyKeyboardMarkup([["Скасувати"]], resize_keyboard=True))
        return RSTART
    if t == "Щоденне без кінцевої дати":
        await update.message.reply_text("Час (HH:MM):", reply_markup=ReplyKeyboardMarkup([["Скасувати"]], resize_keyboard=True))
        return RTIME

async def rem_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["start_date"] = update.message.text.strip()
    await update.message.reply_text("Дата завершення (YYYY-MM-DD):")
    return REND

async def rem_end_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["end_date"] = update.message.text.strip()
    await update.message.reply_text("Час (HH:MM):")
    return RTIME

async def send_text(bot, chat_id, thread_id, text):
    if thread_id is None:
        await bot.send_message(chat_id=chat_id, text=text)
    else:
        await bot.send_message(chat_id=chat_id, message_thread_id=thread_id, text=text)

async def reminder_job(application, rem):
    if not rem.get("active", True): return
    bot = application.bot
    if rem.get("for_all_open"):
        for t in list_open_threads():
            try: await send_text(bot, t["chat_id"], t["id"], rem["text"])
            except: pass
    else:
        try: await send_text(bot, rem["chat_id"], rem.get("thread_id"), rem["text"])
        except: pass

def schedule_reminder(scheduler, application, rem):
    job_ids = []
    rtype = rem["rtype"]
    if rtype == "Одноразове":
        spec = rem["time_spec"]
        when = None
        if spec.startswith("+"):
            mins = int(spec[1:].strip())
            when = datetime.now(TZ) + timedelta(minutes=mins)
        else:
            hh, mm = map(int, spec.split(":"))
            now = datetime.now(TZ)
            when = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if when < now: when += timedelta(days=1)
        j = scheduler.add_job(lambda: asyncio.create_task(reminder_job(application, rem)), "date", run_date=when)
        job_ids.append(j.id)
    elif rtype == "Щоденне з датами":
        hh, mm = map(int, rem["time"].split(":"))
        async def daily_window():
            today = datetime.now(TZ).date()
            sd = datetime.strptime(rem["start_date"], "%Y-%m-%d").date()
            ed = datetime.strptime(rem["end_date"], "%Y-%m-%d").date()
            if sd <= today <= ed:
                await reminder_job(application, rem)
        j = scheduler.add_job(lambda: asyncio.create_task(daily_window()), "cron", hour=hh, minute=mm)
        job_ids.append(j.id)
    elif rtype == "Щоденне без кінцевої дати":
        hh, mm = map(int, rem["time"].split(":"))
        j = scheduler.add_job(lambda: asyncio.create_task(reminder_job(application, rem)), "cron", hour=hh, minute=mm)
        job_ids.append(j.id)
    rem["job_ids"] = job_ids
    upsert_reminder(rem)

def schedule_all(scheduler, application):
    for rem in get_reminders(active_only=True):
        schedule_reminder(scheduler, application, rem)

async def rem_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if txt == "Скасувати":
        await update.message.reply_text("Скасовано.", reply_markup=MAIN_KB); return ConversationHandler.END
    rtype = context.user_data["rtype"]
    rem = {
        "id": "rem_" + uuid.uuid4().hex[:10],
        "title": context.user_data["title"],
        "text": context.user_data["text"],
        "rtype": rtype,
        "active": True
    }
    target = context.user_data["target"]
    if target["mode"] == "all_open":
        rem["for_all_open"] = True
        rem["chat_id"] = update.effective_chat.id
        rem["thread_id"] = None
    else:
        rem["for_all_open"] = False
        rem["chat_id"] = update.effective_chat.id
        rem["thread_id"] = target.get("thread_id")
    if rtype == "Одноразове":
        rem["time_spec"] = txt
    elif rtype == "Щоденне з датами":
        rem["start_date"] = context.user_data["start_date"]
        rem["end_date"] = context.user_data["end_date"]
        rem["time"] = txt
    elif rtype == "Щоденне без кінцевої дати":
        rem["time"] = txt
    upsert_reminder(rem)
    schedule_reminder(scheduler, application, rem)  # uses globals below
    await update.message.reply_text("✅ Нагадування створено.", reply_markup=MAIN_KB)
    return ConversationHandler.END

async def disable_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rems = get_reminders(active_only=True)
    if not rems:
        await update.message.reply_text("Активних нагадувань немає.", reply_markup=MAIN_KB); return
    rows = [[r["title"]] for r in rems] + [["Скасувати"]]
    await update.message.reply_text("Оберіть нагадування для вимкнення:", reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True))

async def remove_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.message.text
    if title == "Скасувати":
        await update.message.reply_text("Скасовано.", reply_markup=MAIN_KB); return
    rems = get_reminders(active_only=True)
    found = [r for r in rems if r["title"] == title]
    if not found:
        await update.message.reply_text("Не знайшов таке активне нагадування.", reply_markup=MAIN_KB); return
    ok = deactivate_reminder_by_title(title)
    if ok:
        for r in found:
            for jid in r.get("job_ids", []):
                try: scheduler.remove_job(jid)
                except: pass
        await update.message.reply_text(f"🛑 «{title}» вимкнено.", reply_markup=MAIN_KB)
    else:
        await update.message.reply_text("Не вдалось вимкнути.", reply_markup=MAIN_KB)

application = None
scheduler = AsyncIOScheduler(timezone=TZ)

TOKEN = os.getenv("BOT_TOKEN")
application = ApplicationBuilder().token(TOKEN).build()

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
    entry_points=[MessageHandler(filters.Regex("^⏰ Створити нагадування$"), rem_start_flow)],
    states={
        RTARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, rem_target)],
        RSELECT_THREAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, rem_select_thread)],
        RTITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, rem_title)],
        RTEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, rem_text)],
        RTYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, rem_type)],
        RSTART: [MessageHandler(filters.TEXT & ~filters.COMMAND, rem_start_date)],
        REND: [MessageHandler(filters.TEXT & ~filters.COMMAND, rem_end_date)],
        RTIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, rem_time)],
    },
    fallbacks=[],
)

application.add_handler(CommandHandler("start", start))
application.add_handler(conv_task)
application.add_handler(conv_rem)
application.add_handler(MessageHandler(filters.Regex("^✅ Закрити задачу$"), close_task))
application.add_handler(MessageHandler(filters.Regex("^🛑 Вимкнути нагадування$"), disable_reminders))
application.add_handler(MessageHandler(filters.Regex("^🛑 "), remove_reminder))
application.add_handler(MessageHandler(filters.Regex("^[^/].*"), lambda u, c: u.message.reply_text("Оберіть дію з клавіатури або /start", reply_markup=MAIN_KB)))

schedule_all(scheduler, application)
scheduler.start()

if __name__ == "__main__":
    print("🤖 Бот запущено!")
    application.run_polling()
