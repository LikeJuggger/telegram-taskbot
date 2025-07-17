import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters
)

# Етапи збору інформації
NAME, DESCRIPTION, LINKS, ASSIGNEE, DEADLINE = range(5)

# Команди
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привіт! Напиши /newtask щоб створити нову задачу.")

async def new_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📌 Назва задачі?")
    return NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("📝 Опиши суть задачі:")
    return DESCRIPTION

async def get_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['description'] = update.message.text
    await update.message.reply_text("📎 Додай посилання або напиши «немає»")
    return LINKS

async def get_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['links'] = update.message.text
    await update.message.reply_text("👤 Хто виконавець? Вкажи @username:")
    return ASSIGNEE

async def get_assignee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['assignee'] = update.message.text
    await update.message.reply_text("⏰ Який дедлайн?")
    return DEADLINE

async def get_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['deadline'] = update.message.text
    data = context.user_data

    summary = (
        f"✅ *Нова задача!*\n\n"
        f"*Назва:* {data['name']}\n"
        f"*Опис:* {data['description']}\n"
        f"*Матеріали:* {data['links']}\n"
        f"*Виконавець:* {data['assignee']}\n"
        f"*Дедлайн:* {data['deadline']}"
    )

    await update.message.reply_markdown(summary)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Задачу скасовано.")
    return ConversationHandler.END

# ✅ Код стартує завжди (без if __name__ == '__main__')
TOKEN = os.getenv("BOT_TOKEN")
app = ApplicationBuilder().token(TOKEN).build()

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
)

app.add_handler(CommandHandler("start", start))
app.add_handler(conv)

print("🤖 Бот запущено!")
app.run_polling()
