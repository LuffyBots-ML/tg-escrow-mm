#!/usr/bin/env python3
"""
es.py - Termux-ready Escrow Bot (sqlite)
Replace BOT_TOKEN & OWNER_ID below if needed.
"""
import os
import logging
import random
import time
import sqlite3
import re
import html
from functools import wraps
from telegram import Update, ParseMode
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# ----------------- CONFIG -----------------
BOT_TOKEN = "8493143907:AAGRK-N0Ss21MEREGV65hrIW7vyYKiTDTlI"
OWNER_ID = 6847499628
PW_BY = "@LuffyBots"
DB_FILE = "escrow.db"
ADMINS = set([OWNER_ID])  # will be persisted only in DB (but keep owner always admin)
TRADE_ID_PREFIX = "TID"
# ------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ---------- DB helpers & migration ----------
def get_conn():
    return sqlite3.connect(DB_FILE, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    # create main table if not exists (safe create)
    c.execute("""
    CREATE TABLE IF NOT EXISTS deals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trade_id TEXT UNIQUE,
        chat_id INTEGER,
        bot_message_id INTEGER,
        amount REAL,
        buyer TEXT,
        seller TEXT,
        escrower_id INTEGER,
        status TEXT,
        refunded_amount REAL DEFAULT 0,
        created_at INTEGER,
        closed_at INTEGER
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY
    )
    """)
    # ensure owner exists in admins table
    c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (OWNER_ID,))
    conn.commit()
    conn.close()

def db_execute(query, params=(), fetch=False):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return rows

init_db()

# ---------- utilities ----------
def is_owner(user_id):
    return int(user_id) == int(OWNER_ID)

def is_admin(user_id):
    if user_id is None:
        return False
    if int(user_id) == int(OWNER_ID):
        return True
    rows = db_execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,), fetch=True)
    return bool(rows)

def owner_only(func):
    @wraps(func)
    def wrapped(update: Update, context: CallbackContext, *a, **kw):
        uid = update.effective_user.id if update.effective_user else None
        if not is_owner(uid):
            update.message.reply_text("❌ Only the owner can use this command.")
            return
        return func(update, context, *a, **kw)
    return wrapped

def admin_only(func):
    @wraps(func)
    def wrapped(update: Update, context: CallbackContext, *a, **kw):
        uid = update.effective_user.id if update.effective_user else None
        if not is_admin(uid):
            update.message.reply_text("⚠️ Only owner or bot admins can use this command.")
            return
        return func(update, context, *a, **kw)
    return wrapped

def gen_trade_id():
    return TRADE_ID_PREFIX + str(random.randint(100000, 999999))

def norm_user_arg(u):
    if not u:
        return None
    u = u.strip()
    if u.startswith("@"):
        return u
    if u.isdigit():
        return u
    # fallback: raw text
    return u

def format_deal_text(header, amount, buyer, seller, trade_id, escrow_mention):
    b = html.escape(str(buyer))
    s = html.escape(str(seller))
    esc = html.escape(str(escrow_mention))
    text = (
        "<b>Deal Details 👇</b>\n\n"
        f"{header}\n\n"
        f"<b>Total Deal Amount :</b> ₹{amount}\n"
        f"<b>Buyer :</b> {b}\n"
        f"<b>Seller :</b> {s}\n"
        f"<b>Trade ID :</b> #{trade_id}\n\n"
        f"PW BY : {PW_BY}\n"
        f"<b>Escrowed By :</b> {esc}"
    )
    return text

def find_open_deal(chat_id, amount, buyer, seller):
    rows = db_execute("SELECT trade_id, bot_message_id, amount, buyer, seller FROM deals WHERE chat_id=? AND status='OPEN'", (chat_id,), fetch=True)
    if not rows:
        return None
    for r in rows:
        tid, bot_msg_id, amt, b, s = r
        try:
            if float(amt) != float(amount):
                continue
        except:
            continue
        # compare buyer/seller loosely (case-insensitive exact)
        if str(b).lower() != str(buyer).lower():
            continue
        if str(s).lower() != str(seller).lower():
            continue
        return tid, bot_msg_id
    return None

# ---------- command handlers ----------
def start(update: Update, context: CallbackContext):
    txt = (
        "✨ LB Escrow Bot ready.\n\n"
        "Admin commands (owner/admin only):\n"
        "/add <amount> <@buyer> <@seller>\n"
        "/close <TID|amount @buyer @seller>\n"
        "/refund <TID|amount @buyer @seller>\n"
        "/cancel <TID|amount @buyer @seller>\n\n"
        "Other: /status <TID>  /deals  /estats [escrower_id]  /id"
    )
    update.message.reply_text(txt)

def id_cmd(update: Update, context: CallbackContext):
    uid = update.effective_user.id if update.effective_user else "unknown"
    update.message.reply_text(f"Your ID: {uid}")

@owner_only
def addadmin(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Usage: /addadmin <user_id>")
        return
    try:
        uid = int(context.args[0])
        db_execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (uid,))
        update.message.reply_text(f"✅ Added admin: {uid}")
    except Exception as e:
        update.message.reply_text("Invalid user id.")

@owner_only
def removeadmin(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Usage: /removeadmin <user_id>")
        return
    try:
        uid = int(context.args[0])
        db_execute("DELETE FROM admins WHERE user_id=?", (uid,))
        update.message.reply_text(f"✅ Removed admin: {uid}")
    except Exception as e:
        update.message.reply_text("Invalid user id.")

@admin_only
def adminlist(update: Update, context: CallbackContext):
    rows = db_execute("SELECT user_id FROM admins", fetch=True)
    if not rows:
        update.message.reply_text("No admins.")
        return
    text = "Admins:\n" + "\n".join(str(r[0]) for r in rows)
    update.message.reply_text(text)

def _handle_action(update: Update, context: CallbackContext, action: str):
    """
    action in {'ADD','CLOSE','REFUND','CANCEL'}
    Syntax:
      /add <amount> <@buyer> <@seller>
      /close <TID>   OR /close <amount> <@buyer> <@seller>
    """
    msg = update.message
    user = update.effective_user
    if not user:
        return
    chat_id = msg.chat_id

    if len(context.args) < 1:
        msg.reply_text(f"Usage: /{action.lower()} <amount> <@buyer> <@seller>  OR /{action.lower()} <TIDxxxxxx>")
        return

    first = context.args[0]

    # If first arg is TID, find by id
    tid = None
    bot_msg_id = None
    if re.match(r"^#?TID\d{6,7}$", first.upper()):
        tid = first.upper().lstrip("#")
        row = db_execute("SELECT trade_id, chat_id, bot_message_id, amount, buyer, seller FROM deals WHERE trade_id=?", (tid,), fetch=True)
        if not row:
            msg.reply_text("❌ Trade not found.")
            return
        rec = row[0]
        tid, rchat, bot_msg_id, amount, buyer, seller = rec[0], rec[1], rec[2], rec[3], rec[4], rec[5]
    else:
        # normal path: amount buyer seller
        if len(context.args) < 3:
            msg.reply_text("Usage: /{cmd} <amount> <@buyer> <@seller>".format(cmd=action.lower()))
            return
        try:
            amount = float(context.args[0])
        except:
            msg.reply_text("Enter numeric amount.")
            return
        buyer = norm_user_arg(context.args[1])
        seller = norm_user_arg(context.args[2])

        # For ADD -> create new trade
        if action == "ADD":
            tid = gen_trade_id()
            escrow_mention = ("@" + user.username) if user.username else user.first_name
            header = "✅ Payment received\nContinue your deal ✅"
            text = format_deal_text(header, amount, buyer, seller, tid, escrow_mention)
            try:
                sent = context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
                db_execute("INSERT INTO deals (trade_id, chat_id, bot_message_id, amount, buyer, seller, escrower_id, status, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                           (tid, chat_id, sent.message_id, amount, buyer, seller, user.id, "OPEN", int(time.time())))
                msg.reply_text(f"✅ Deal created. Trade ID: #{tid}")
            except Exception as e:
                logger.exception("Failed to post deal: %s", e)
                msg.reply_text("Failed to create deal (bot needs permission to send messages).")
            return
        else:
            # For CLOSE/REFUND/CANCEL we try to find open matching deal
            found = find_open_deal(chat_id, amount, buyer, seller)
            if not found:
                msg.reply_text("❌ No matching open deal found in this chat. Use Trade ID or exact @username + amount.")
                return
            tid, bot_msg_id = found
            row = db_execute("SELECT amount, buyer, seller FROM deals WHERE trade_id=?", (tid,), fetch=True)[0]
            amount, buyer, seller = row[0], row[1], row[2]

    # Now we have tid, bot_msg_id (if exists), amount, buyer, seller
    # Fetch escrower id if stored
    escrow_row = db_execute("SELECT escrower_id FROM deals WHERE trade_id=?", (tid,), fetch=True)
    escrower_id = escrow_row[0][0] if escrow_row else None
    escrow_mention = None
    if escrower_id:
        try:
            member = context.bot.get_chat_member(chat_id, escrower_id).user
            escrow_mention = ("@" + member.username) if member and member.username else (member.first_name if member else ("@" + user.username if user.username else user.first_name))
        except Exception:
            escrow_mention = ("@" + user.username) if user.username else user.first_name
    else:
        escrow_mention = ("@" + user.username) if user.username else user.first_name

    if action == "CLOSE":
        db_execute("UPDATE deals SET status=?, closed_at=? WHERE trade_id=?", ("CLOSED", int(time.time()), tid))
        header = "Deal Closed ✅"
        text = format_deal_text(header, amount, buyer, seller, tid, escrow_mention)
        try:
            if bot_msg_id:
                context.bot.edit_message_text(chat_id=chat_id, message_id=bot_msg_id, text=text, parse_mode=ParseMode.HTML)
            else:
                context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.info("edit failed: %s", e)
            context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
        msg.reply_text(f"✅ Deal #{tid} closed.")
        return

    if action == "REFUND":
        db_execute("UPDATE deals SET status=?, refunded_amount=?, closed_at=? WHERE trade_id=?", ("REFUNDED", amount, int(time.time()), tid))
        header = "Deal Refunded 💸"
        text = format_deal_text(header, amount, buyer, seller, tid, escrow_mention)
        try:
            if bot_msg_id:
                context.bot.edit_message_text(chat_id=chat_id, message_id=bot_msg_id, text=text, parse_mode=ParseMode.HTML)
            else:
                context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.info("edit failed: %s", e)
            context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
        msg.reply_text(f"✅ Deal #{tid} refunded (₹{amount}).")
        return

    if action == "CANCEL":
        db_execute("UPDATE deals SET status=?, closed_at=? WHERE trade_id=?", ("CANCELLED", int(time.time()), tid))
        header = "Deal Cancelled ❌"
        text = format_deal_text(header, amount, buyer, seller, tid, escrow_mention)
        try:
            if bot_msg_id:
                context.bot.edit_message_text(chat_id=chat_id, message_id=bot_msg_id, text=text, parse_mode=ParseMode.HTML)
            else:
                context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.info("edit failed: %s", e)
            context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
        msg.reply_text(f"✅ Deal #{tid} cancelled.")
        return

# wrappers
@admin_only
def cmd_add(update: Update, context: CallbackContext):
    return _handle_action(update, context, "ADD")

@admin_only
def cmd_close(update: Update, context: CallbackContext):
    return _handle_action(update, context, "CLOSE")

@admin_only
def cmd_refund(update: Update, context: CallbackContext):
    return _handle_action(update, context, "REFUND")

@admin_only
def cmd_cancel(update: Update, context: CallbackContext):
    return _handle_action(update, context, "CANCEL")

def status_cmd(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Usage: /status <TIDxxxxxx>")
        return
    tid = context.args[0].upper().lstrip("#")
    row = db_execute("SELECT trade_id,status,amount,buyer,seller,created_at,closed_at FROM deals WHERE trade_id=?", (tid,), fetch=True)
    if not row:
        update.message.reply_text("Trade not found.")
        return
    r = row[0]
    update.message.reply_text(f"Trade {r[0]} | Status: {r[1]} | Amount: ₹{r[2]} | Buyer: {r[3]} | Seller: {r[4]}")

def deals_cmd(update: Update, context: CallbackContext):
    rows = db_execute("SELECT trade_id,status,amount,created_at FROM deals ORDER BY created_at DESC LIMIT 30", fetch=True)
    if not rows:
        update.message.reply_text("No deals yet.")
        return
    text = "\n".join([f"{r[0]} | {r[1]} | ₹{r[2]}" for r in rows])
    update.message.reply_text(text)

def estats_cmd(update: Update, context: CallbackContext):
    arg = context.args[0] if context.args else None
    try:
        eid = int(arg) if arg else update.effective_user.id
    except:
        update.message.reply_text("Provide numeric escrower id.")
        return
    rows = db_execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM deals WHERE escrower_id=? AND status='CLOSED'", (eid,), fetch=True)
    cnt, total = rows[0] if rows else (0, 0)
    update.message.reply_text(f"Escrower {eid} closed {cnt} deals, Total amount: ₹{total}")

def unknown(update: Update, context: CallbackContext):
    update.message.reply_text("Unknown command. Use /start to see help.")

# ---------- main ----------
def main():
    init_db()
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("id", id_cmd))
    dp.add_handler(CommandHandler("help", start))
    dp.add_handler(CommandHandler("addadmin", addadmin))
    dp.add_handler(CommandHandler("removeadmin", removeadmin))
    dp.add_handler(CommandHandler("adminlist", adminlist))
    dp.add_handler(CommandHandler("add", cmd_add))
    dp.add_handler(CommandHandler("close", cmd_close))
    dp.add_handler(CommandHandler("refund", cmd_refund))
    dp.add_handler(CommandHandler("cancel", cmd_cancel))
    dp.add_handler(CommandHandler("status", status_cmd))
    dp.add_handler(CommandHandler("deals", deals_cmd))
    dp.add_handler(CommandHandler("estats", estats_cmd))

    dp.add_handler(MessageHandler(Filters.command, unknown))

    logger.info("Starting escrow bot...")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
