import os
import random
import string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMemberUpdated
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters, ConversationHandler, ChatMemberHandler
from telegram.constants import ChatMemberStatus
from dotenv import load_dotenv
from datetime import datetime, timedelta
import threading
from flask import Flask

# Initialize Flask app
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return 'Bot is running'

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    flask_app.run(host='0.0.0.0', port=port)

# Load environment variables
load_dotenv()

# In-memory storage
users = {}

# Admin Information
ADMIN_USERNAME = "star_ies1"
ADMIN_ID = 7302005705
ANNOUNCEMENT_CHANNEL = "@latestinfoult"

# Constants
WELCOME_BONUS = 100  # ₦100
REFERRAL_BONUS = 80  # ₦80
DAILY_BONUS = 25  # ₦25
MIN_WITHDRAWAL = 500  # ₦500
MAX_WITHDRAWAL = 1000  # ₦1000
LEAVE_PENALTY = 200  # ₦200
CHAT_REWARD = 1  # ₦1
MAX_DAILY_CHAT_REWARD = 50  # ₦50
TASK_REWARD = 100  # ₦100
WITHDRAWAL_AMOUNTS = [500, 1000, 1500]

# Channel and Group IDs
CHANNEL_USERNAME = "latestinfoult"
GROUP_USERNAME = "-1002250504941"
REQUIRED_CHANNEL = f"@{CHANNEL_USERNAME}"
REQUIRED_GROUP = f"https://t.me/+aeseN6uPGikzMDM0"
BOT_USERNAME = "sub9ja_bot"

# Common Nigerian Banks
BANKS = [
    'Access Bank', 'First Bank', 'GT Bank', 'UBA', 'Zenith Bank',
    'Fidelity Bank', 'Union Bank', 'Sterling Bank', 'Wema Bank',
    'Stanbic IBTC', 'Polaris Bank', 'Opay', 'Palmpay', 'Kuda'
]

# Conversation states
(WITHDRAWAL_AMOUNT, ACCOUNT_NAME, BANK_NAME, ACCOUNT_NUMBER, PAYMENT_SCREENSHOT) = range(5)

def get_user_data(user_id):
    if user_id not in users:
        users[user_id] = {
            'balance': 0,
            'referrals': [],
            'last_signin': None,
            'last_withdrawal': None,
            'is_verified': False
        }
    return users[user_id]

def update_user_balance(user_id, amount):
    user_data = get_user_data(user_id)
    user_data['balance'] += amount
    return user_data['balance']

def get_user_balance(user_id):
    user_data = get_user_data(user_id)
    return user_data['balance']

def add_referral(referrer_id, referred_id):
    user_data = get_user_data(referrer_id)
    if referred_id not in user_data['referrals']:
        user_data['referrals'].append(referred_id)
        update_user_balance(referrer_id, REFERRAL_BONUS)

def get_referral_count(referrer_id):
    user_data = get_user_data(referrer_id)
    return len(user_data['referrals'])

def check_and_credit_daily_bonus(user_id):
    user_data = get_user_data(user_id)
    today = datetime.now().date()
    
    if not user_data['last_signin'] or user_data['last_signin'].date() < today:
        user_data['last_signin'] = datetime.now()
        update_user_balance(user_id, DAILY_BONUS)
        return True
    return False

async def check_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        channel_member = await context.bot.get_chat_member(chat_id=f"@{CHANNEL_USERNAME}", user_id=user_id)
        group_member = await context.bot.get_chat_member(chat_id=REQUIRED_GROUP, user_id=user_id)
        
        return (channel_member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER] and
                group_member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER])
    except Exception:
        return False

async def handle_verify_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer("🔍 Checking membership status...")
    
    try:
        await query.message.edit_text(
            "⏳ Verifying your membership...\n"
            "Please wait a moment."
        )
        
        is_member = await check_membership(user_id, context)
        if not is_member:
            keyboard = [
                [
                    InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME}"),
                    InlineKeyboardButton("👥 Join Group", url=REQUIRED_GROUP)
                ],
                [InlineKeyboardButton("🔄 Try Again", callback_data='verify_membership')]
            ]
            await query.message.edit_text(
                "❌ Verification Failed!\n\n"
                "Please make sure to:\n"
                "1. Join our channel\n"
                "2. Join our group\n"
                "3. Stay in both\n\n"
                "Then click 'Try Again'",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        user_data = get_user_data(user_id)
        is_new_user = not user_data['is_verified']
        
        if is_new_user:
            await query.message.edit_text(
                "✅ Verification Successful!\n\n"
                f"🎁 You received ₦{WELCOME_BONUS} welcome bonus!\n"
                "Loading your dashboard..."
            )
            update_user_balance(user_id, WELCOME_BONUS)
            user_data['is_verified'] = True
        
        # Check for daily bonus
        daily_bonus_earned = check_and_credit_daily_bonus(user_id)
        if daily_bonus_earned:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📅 Daily Bonus!\nYou earned ₦{DAILY_BONUS} for logging in today!"
            )
        
        # Show dashboard
        await show_dashboard(update, context)
            
    except Exception as e:
        print(f"Verification error: {e}")
        await query.message.edit_text(
            "❌ An error occurred during verification.\n"
            "Please try again later.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Try Again", callback_data='verify_membership')]
            ])
        )

async def show_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE, show_back=False):
    user = update.effective_user
    balance = get_user_balance(user.id)
    ref_count = get_referral_count(user.id)
    
    keyboard = [
        [
            InlineKeyboardButton("👥 Referrals", callback_data='my_referrals'),
            InlineKeyboardButton("💰 Balance", callback_data='balance'),
            InlineKeyboardButton("🏆 Top Referrals", callback_data='top_referrals')
        ],
        [
            InlineKeyboardButton("🎯 Get Link", callback_data='get_link'),
            InlineKeyboardButton("💸 Withdraw", callback_data='withdraw'),
            InlineKeyboardButton("📝 Submit Task", callback_data='submit_task')
        ],
        [
            InlineKeyboardButton("📅 Daily Bonus", callback_data='daily_bonus'),
            InlineKeyboardButton("📋 My Tasks", callback_data='tasks'),
            InlineKeyboardButton("💬 Support", callback_data='support')
        ]
    ]
    
    if show_back:
        keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    dashboard_text = (
        "🤖 Welcome to Sub9ja Bot!\n"
        "Earn rewards through referrals, tasks & more.\n"
        "──────────────────\n\n"
        "👤 Your Stats:\n"
        f"• Balance: ₦{balance}\n"
        f"• Referrals: {ref_count} (₦{ref_count * REFERRAL_BONUS} earned)\n\n"
        "💎 Available Rewards:\n"
        f"• Welcome Bonus: ₦{WELCOME_BONUS}\n"
        f"• Per Referral: ₦{REFERRAL_BONUS}\n"
        f"• Daily Login: ₦{DAILY_BONUS}\n"
        f"• Chat Messages: ₦1 each (max ₦{MAX_DAILY_CHAT_REWARD}/day)\n"
        f"• Min. Withdrawal: ₦{MIN_WITHDRAWAL}\n\n"
        "Select an option below:"
    )
    
    if update.callback_query:
        await update.callback_query.message.edit_text(
            dashboard_text,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            dashboard_text,
            reply_markup=reply_markup
        )

async def handle_withdrawal_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    balance = user_data['balance']
    
    # Check if user can withdraw today
    if user_data['last_withdrawal'] and user_data['last_withdrawal'].date() == datetime.now().date():
        await update.message.reply_text(
            "❌ You can only withdraw once per day!\n"
            "Please try again tomorrow."
        )
        return ConversationHandler.END
    
    if balance < MIN_WITHDRAWAL:
        await update.message.reply_text(
            f"❌ You need at least ₦{MIN_WITHDRAWAL} to withdraw.\n"
            f"Your current balance: ₦{balance}"
        )
        return ConversationHandler.END
    
    max_allowed = min(balance, MAX_WITHDRAWAL)
    await update.message.reply_text(
        f"💰 Enter withdrawal amount:\n\n"
        f"Minimum: ₦{MIN_WITHDRAWAL}\n"
        f"Maximum: ₦{max_allowed}\n"
        f"Your balance: ₦{balance}\n\n"
        f"Please enter an amount between ₦{MIN_WITHDRAWAL} and ₦{max_allowed}:"
    )
    return WITHDRAWAL_AMOUNT

if __name__ == "__main__":
    # Start the Flask server in a separate thread
    server_thread = threading.Thread(target=run_flask)
    server_thread.start()
    
    # Start the bot
    app = Application.builder().token(os.getenv('BOT_TOKEN')).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", show_dashboard))
    app.add_handler(CallbackQueryHandler(handle_verify_membership, pattern="^verify_membership$"))
    
    # Start the bot
    print("Bot is running...")
    app.run_polling()