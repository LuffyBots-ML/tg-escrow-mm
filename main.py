from telegram.ext import Updater, CommandHandler
import json
import os

DEALS_FILE = "deals.json"

def load_deals():
    if os.path.exists(DEALS_FILE):
        with open(DEALS_FILE, "r") as f:
            return json.load(f)
    return []

def save_deals(deals):
    with open(DEALS_FILE, "w") as f:
        json.dump(deals, f)

def add(update, context):
    deals = load_deals()
    if not context.args:
        update.message.reply_text("Usage: /add <amount>")
        return
    amount = context.args[0]
    buyer = update.effective_user.username or str(update.effective_user.id)
    deal = {
        "trade_id": f"TID{len(deals)+1:06d}",
        "buyer": buyer,
        "amount": amount,
        "status": "open"
    }
    deals.append(deal)
    save_deals(deals)
    update.message.reply_text(
        f"✅ Deal Created!
"
        f"Trade ID: {deal['trade_id']}
"
        f"Buyer: {deal['buyer']}
"
        f"Amount: ₹{deal['amount']}
"
        f"Status: {deal['status']}"
    )

def close(update, context):
    deals = load_deals()
    if not context.args:
        update.message.reply_text("Usage: /close <amount>")
        return
    amount = context.args[0]
    buyer = update.effective_user.username or str(update.effective_user.id)
    # Find open deal with this amount and buyer
    for deal in deals:
        if deal["buyer"] == buyer and deal["amount"] == amount and deal["status"] == "open":
            deal["status"] = "closed"
            save_deals(deals)
            update.message.reply_text(
                f"✅ Deal Closed!
"
                f"Trade ID: {deal['trade_id']}
"
                f"Amount: ₹{deal['amount']}"
            )
            return
    update.message.reply_text("No open deal found with this amount.")

def main():
    updater = Updater("8203190461:AAETGvU-I2ogfYrD7QorZRmq2i4LOfu1JiI", use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("add", add))
    dp.add_handler(CommandHandler("close", close))
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
