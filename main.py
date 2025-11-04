import sqlite3
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# Set up logging (for debugging)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot configuration (your details)
BOT_TOKEN = '7894521614:AAGrD7yGyyV3CyGcMBBjhVVuh04kRMXfBYQ'
OWNER_ID = 6847499628  # your Telegram numeric ID

# Connect to SQLite database (create file escrow_bot.db if not exists)
conn = sqlite3.connect('escrow_bot.db', check_same_thread=False)
cursor = conn.cursor()

# Create tables: deals (to store escrow deals) and admins (to store admin user IDs)
cursor.execute('''
    CREATE TABLE IF NOT EXISTS deals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tid TEXT UNIQUE,
        amount REAL,
        buyer_id INTEGER,
        buyer_username TEXT,
        seller_id INTEGER,
        seller_username TEXT,
        escrower_id INTEGER,
        escrower_username TEXT,
        status TEXT,
        created_at TEXT,
        closed_at TEXT
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY
    )
''')
conn.commit()

# /add <amount> <@buyer> <@seller>: Start a new deal
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if len(context.args) != 3:
        await update.message.reply_text("Usage: /add <amount> <@buyer> <@seller>")
        return
    try:
        amount = float(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid amount. Usage: /add <amount> <@buyer> <@seller>")
        return

    buyer = context.args[1].lstrip('@')
    seller = context.args[2].lstrip('@')
    escrower_id = user.id
    escrower_username = user.username or user.first_name
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "Open"

    cursor.execute(
        'INSERT INTO deals (amount, buyer_username, seller_username, escrower_id, escrower_username, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (amount, buyer, seller, escrower_id, escrower_username, status, created_at)
    )
    deal_id = cursor.lastrowid
    tid = f"#TID{deal_id:06d}"
    cursor.execute('UPDATE deals SET tid=? WHERE id=?', (tid, deal_id))
    conn.commit()

    message = (
        f"✅ New deal created:\n"
        f"TID: {tid}\n"
        f"Buyer: @{buyer}\n"
        f"Seller: @{seller}\n"
        f"Amount: ₹{amount}\n"
        f"Escrowed By: @{escrower_username}\n"
        f"Status: {status}\n"
        f"Created: {created_at}"
    )
    await update.message.reply_text(message)

# /close <TID> or /close <amount> <@buyer> <@seller>
async def close(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Usage: /close <TID> or /close <amount> <@buyer> <@seller>")
        return

    tid_arg = context.args[0]
    if tid_arg.startswith("#TID"):
        tid = tid_arg
        cursor.execute('SELECT * FROM deals WHERE tid=?', (tid,))
    else:
        if len(context.args) != 3:
            await update.message.reply_text("Usage: /close <TID> or /close <amount> <@buyer> <@seller>")
            return
        try:
            amount = float(context.args[0])
        except ValueError:
            await update.message.reply_text("Invalid usage. Provide TID or /close <amount> <@buyer> <@seller>")
            return
        buyer = context.args[1].lstrip('@')
        seller = context.args[2].lstrip('@')
        cursor.execute(
            'SELECT * FROM deals WHERE amount=? AND buyer_username=? AND seller_username=? AND status="Open"',
            (amount, buyer, seller)
        )

    deal = cursor.fetchone()
    if not deal:
        await update.message.reply_text("Deal not found or already closed.")
        return

    (deal_id, tid, amount, buyer_id, buyer_username, seller_id, seller_username,
     escrower_id, escrower_username, status, created_at, closed_at) = deal

    cursor.execute('SELECT 1 FROM admins WHERE user_id=?', (user.id,))
    is_admin = cursor.fetchone() is not None
    if user.id != escrower_id and user.id != OWNER_ID and not is_admin:
        await update.message.reply_text("You do not have permission to close this deal.")
        return
    if status != "Open":
        await update.message.reply_text(f"Deal {tid} is already closed.")
        return

    closed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('UPDATE deals SET status=?, closed_at=? WHERE id=?', ("Closed", closed_at, deal_id))
    conn.commit()
    message = (
        f"✅ Deal Closed ✅\n"
        f"TID: {tid}\n"
        f"Buyer: @{buyer_username}\n"
        f"Seller: @{seller_username}\n"
        f"Amount: ₹{amount}\n"
        f"Escrowed By: @{escrower_username}\n"
        f"Status: Closed\n"
        f"Closed: {closed_at}"
    )
    await update.message.reply_text(message)

# /ongoing: list all open deals
async def ongoing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cursor.execute("SELECT tid, buyer_username, seller_username, amount, escrower_username, created_at FROM deals WHERE status='Open'")
    deals = cursor.fetchall()
    if not deals:
        await update.message.reply_text("No open deals found.")
        return
    lines = ["📋 *Open Deals:*"]
    for tid, buyer, seller, amount, escrower, created_at in deals:
        lines.append(f"{tid}: @{buyer} → @{seller}, ₹{amount}, by @{escrower}, {created_at}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# /stats: personal escrow stats
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    cursor.execute('SELECT COUNT(*) FROM deals WHERE escrower_id=?', (user.id,))
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM deals WHERE escrower_id=? AND status='Closed'", (user.id,))
    closed = cursor.fetchone()[0]
    await update.message.reply_text(f"📊 Stats for @{user.username or user.first_name}\nTotal Deals: {total}\nClosed: {closed}\nOpen: {total - closed}")

# /status <TID>: check deal
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /status <TID>")
        return
    tid = context.args[0].upper()
    if not tid.startswith("#TID"):
        tid = "#TID" + tid
    cursor.execute('SELECT * FROM deals WHERE tid=?', (tid,))
    deal = cursor.fetchone()
    if not deal:
        await update.message.reply_text("Deal not found.")
        return
    (_, tid, amount, _, buyer, _, seller, _, escrower, status, created_at, closed_at) = deal
    await update.message.reply_text(
        f"🔍 Deal Status:\n"
        f"TID: {tid}\nBuyer: @{buyer}\nSeller: @{seller}\nAmount: ₹{amount}\nEscrowed By: @{escrower}\nStatus: {status}\nCreated: {created_at}\nClosed: {closed_at or '-'}"
    )

# /gstats: global stats
async def gstats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cursor.execute('SELECT COUNT(*) FROM deals')
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM deals WHERE status='Closed'")
    closed = cursor.fetchone()[0]
    await update.message.reply_text(f"🌐 Global Stats\nTotal Deals: {total}\nOpen: {total - closed}\nClosed: {closed}")

# /addadmin and /removeadmin for owner only
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Only the owner can add admins.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /addadmin <user_id>")
        return
    uid = int(context.args[0])
    cursor.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (uid,))
    conn.commit()
    await update.message.reply_text(f"✅ Added admin: {uid}")

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Only the owner can remove admins.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /removeadmin <user_id>")
        return
    uid = int(context.args[0])
    cursor.execute('DELETE FROM admins WHERE user_id=?', (uid,))
    conn.commit()
    await update.message.reply_text(f"✅ Removed admin: {uid}")

# Fallback for unknown commands
async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("❓ Unknown command. Use /add, /close, /ongoing, /status, /stats, /gstats.")

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("close", close))
    app.add_handler(CommandHandler("ongoing", ongoing))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("gstats", gstats))
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("removeadmin", remove_admin))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))
    app.run_polling()

if __name__ == '__main__':
    main()
