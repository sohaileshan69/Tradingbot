import json
import requests
import pandas as pd
import time
from datetime import datetime
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext

# ==============================
# LOAD CONFIG
# ==============================

with open("config.json") as f:
    config = json.load(f)

TELEGRAM_TOKEN = config["TELEGRAM_TOKEN"]
OWNER_USERNAME = config["@Magicianx"]
OWNER_USER_ID = int(config["7365782903"])
CHANNEL_ID = config["-1003326748857"]
PAIRS = config["PAIRS"]
TIMEFRAMES = config["TIMEFRAMES"]
RSI_OVERSOLD = config["RSI_OVERSOLD"]
RSI_OVERBOUGHT = config["RSI_OVERBOUGHT"]
SCORE_THRESHOLD = config["SCORE_THRESHOLD"]
LOOKAHEAD_MINUTES = config["LOOKAHEAD_MINUTES"]

allowed_users = config["allowed_users"]
subscriptions = config["subscriptions"]

bot = Bot(token=TELEGRAM_TOKEN)

PRICE_API = "https://api.binance.com/api/v3/klines"

# ==============================
# SIGNAL LOGIC
# ==============================

def get_price_data(pair, interval="1m", limit=100):
    symbol = pair + "USDT"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    data = requests.get(PRICE_API, params=params).json()

    df = pd.DataFrame(data, columns=[
        "open_time","open","high","low","close","volume",
        "close_time","qav","trades","tbav","tqav","ignore"
    ])

    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)

    return df


def calculate_rsi(df, period=14):
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_ma(df, period=20):
    return df["close"].rolling(period).mean()


def score_signal(df):
    score = 0
    rsi = calculate_rsi(df).iloc[-1]
    ma = calculate_ma(df).iloc[-1]
    close = df["close"].iloc[-1]

    if close > ma:
        score += 30
    if rsi < RSI_OVERSOLD or rsi > RSI_OVERBOUGHT:
        score += 25
    if close > df["close"].iloc[-2]:
        score += 20

    return score


def determine_direction(df):
    if df["close"].iloc[-1] > df["close"].iloc[-2]:
        return "UP ⬆️"
    else:
        return "DOWN ⬇️"


def get_best_signal():
    best_score = 0
    best_pair = None
    best_tf = None
    best_direction = None

    for pair in PAIRS:
        for tf in TIMEFRAMES:
            try:
                df = get_price_data(pair, tf)
                score = score_signal(df)
                if score > best_score:
                    best_score = score
                    best_pair = pair
                    best_tf = tf
                    best_direction = determine_direction(df)
            except:
                pass

    return best_pair, best_tf, best_direction, best_score


# ==============================
# UI KEYBOARD
# ==============================

def main_keyboard(is_owner=False):
    buttons = [[InlineKeyboardButton("🚀 GET SIGNAL", callback_data="get_signal")]]
    if is_owner:
        buttons.append([InlineKeyboardButton("🛠 OWNER PANEL", callback_data="owner_panel")])
    return InlineKeyboardMarkup(buttons)


# ==============================
# START COMMAND
# ==============================

def start(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    is_owner = user_id == OWNER_USER_ID

    update.message.reply_text(
        f"🔥 Trading Signal Bot\n\n"
        f"Owner: {OWNER_USERNAME} 📲\n\n"
        f"Click below to get signal 👇",
        reply_markup=main_keyboard(is_owner)
    )


# ==============================
# BUTTON HANDLER
# ==============================

def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    is_owner = user_id == OWNER_USER_ID

    if query.data == "get_signal":

        # Owner bypass
        if not is_owner:

            if str(user_id) not in allowed_users:
                query.answer("Access Denied ❌")
                query.edit_message_text(
                    f"Access Denied ❌\n\nContact Owner {OWNER_USERNAME} 📲"
                )
                return

            user = allowed_users[str(user_id)]

            # Expiry check
            expiry = datetime.strptime(user["expiry_date"], "%Y-%m-%d").date()
            if datetime.now().date() > expiry:
                query.edit_message_text(
                    f"Subscription Expired ❌\n\nContact Owner {OWNER_USERNAME} 📲"
                )
                return

            # Daily limit check
            if user["used_today"] >= user["daily_limit"]:
                query.edit_message_text(
                    f"Daily Limit Reached ❌\n\nContact Owner {OWNER_USERNAME} 📲"
                )
                return

            user["used_today"] += 1

        pair, tf, direction, score = get_best_signal()

        confidence = int(score)
        emoji = "✅" if confidence > 70 else "⚡"

        message = (
            f"PAIR: {pair} 🎢\n"
            f"TIME: {tf} 🕛\n"
            f"DIRECTION: {direction}\n"
            f"CONFIDENCE: {confidence}% {emoji}\n\n"
            f"Owner: {OWNER_USERNAME} 📲"
        )

        query.edit_message_text(message)


# ==============================
# AUTO CHANNEL SIGNAL LOOP
# ==============================

def auto_signal_loop():
    while True:
        pair, tf, direction, score = get_best_signal()

        if score >= SCORE_THRESHOLD:

            message = (
                f"🔥 AUTO SIGNAL\n\n"
                f"PAIR: {pair}\n"
                f"TIME: {tf}\n"
                f"DIRECTION: {direction}\n"
                f"CONFIDENCE: {score}%\n\n"
                f"Owner: {OWNER_USERNAME} 📲"
            )

            for chat, info in subscriptions.items():

                expiry = datetime.strptime(info["expiry_date"], "%Y-%m-%d").date()

                if info["active"] and datetime.now().date() <= expiry:
                    bot.send_message(chat_id=chat, text=message)
                else:
                    bot.send_message(
                        chat_id=chat,
                        text=f"Signal Disabled ❌\nContact Owner {OWNER_USERNAME} 📲"
                    )

        time.sleep(60)


# ==============================
# RUN BOT
# ==============================

updater = Updater(TELEGRAM_TOKEN, use_context=True)
dp = updater.dispatcher

dp.add_handler(CommandHandler("start", start))
dp.add_handler(CallbackQueryHandler(button_handler))

updater.start_polling()

# Start auto signal loop
import threading
threading.Thread(target=auto_signal_loop).start()

updater.idle()