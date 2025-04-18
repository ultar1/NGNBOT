import os
import random
import string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMemberUpdated, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters, ConversationHandler, ChatMemberHandler
from telegram.constants import ChatMemberStatus
from telegram.helpers import escape_markdown
from dotenv import load_dotenv
from datetime import datetime, timedelta
import asyncio
import logging
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from urllib.parse import urlparse
import time
from telegram.error import TelegramError


# Global state tracking variables
user_quiz_status = {}
user_verification_state = {}
referrals = {}
user_balances = {}
pending_referrals = {}
last_signin = {}
last_withdrawal = {}
user_withdrawal_state = {}
user_bank_info = {}
account_number_to_user = {}
daily_chat_count = {}
last_chat_reward = {}
active_coupons = {}
used_coupons = {}
last_weekly_reward = datetime.now()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()

# Admin Information
ADMIN_USERNAME = "star_ies1"
ADMIN_ID = 7302005705
ANNOUNCEMENT_CHANNEL = "@latestinfoult"  # Channel for announcements

# Store user data in memory
BOT_USERNAME = "sub9ja_bot"  # Updated username

# Channel and Group IDs
CHANNEL_USERNAME = "latestinfoult"
GROUP_USERNAME = "-1002250504941"  # Updated with correct group ID
REQUIRED_CHANNEL = f"@{CHANNEL_USERNAME}"
REQUIRED_GROUP = f"https://t.me/+aeseN6uPGikzMDM0"  # Keep invite link for button

# Constants
WELCOME_BONUS = 50
REFERRAL_BONUS = 80
DAILY_BONUS = 25
TOP_REFERRER_BONUS = 1000
MIN_WITHDRAWAL = 500
MAX_WITHDRAWAL = 1000
LEAVE_PENALTY = 200
CHAT_REWARD = 1
MAX_DAILY_CHAT_REWARD = 50
TASK_REWARD = 250  # Updated from 100 to 250
WITHDRAWAL_AMOUNTS = [500, 1000, 1500]  # Available withdrawal amounts

# Common Nigerian Banks
BANKS = [
    'Access Bank', 'First Bank', 'GT Bank', 'UBA', 'Zenith Bank',
    'Fidelity Bank', 'Union Bank', 'Sterling Bank', 'Wema Bank',
    'Stanbic IBTC', 'Polaris Bank', 'Opay', 'Palmpay', 'Kuda'
]

# Track verified status
user_verified_status = {}

# Define conversation states
(
    ACCOUNT_NUMBER,
    BANK_NAME,
    ACCOUNT_NAME,
    AMOUNT_SELECTION,
    PAYMENT_SCREENSHOT,  # Added payment screenshot state
    LANGUAGE_SELECTION  # Added language selection state
) = range(6)  # Updated range to include new state

LOADING_CHARS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

async def show_loading_animation(message, loading_text="Loading", duration=2):
    """Show a loading animation for the specified duration"""
    start_time = time.time()
    current_frame = 0
    
    while time.time() - start_time < duration:
        frame = LOADING_CHARS[current_frame]
        try:
            await message.edit_text(f"{frame} {loading_text}...")
            current_frame = (current_frame + 1) % len(LOADING_CHARS)
            await asyncio.sleep(0.2)
        except Exception as e:
            logging.error(f"Error updating loading animation: {e}")
            break

def generate_coupon_code(length=8):
    """Generate a random coupon code"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

async def check_and_credit_daily_bonus(user_id: int) -> bool:
    today = datetime.now().date()
    last_date = last_signin.get(user_id)
    
    if last_date is None or last_date < today:
        last_signin[user_id] = today
        update_user_balance(user_id, DAILY_BONUS)
        return True
    return False

async def notify_admin_new_user(user_id: int, user_info: dict, referrer_id: int, context: ContextTypes.DEFAULT_TYPE):
    """
    Notify the admin about a newly verified user.
    """
    try:
        # Fetch user and referrer information
        user = await context.bot.get_chat(user_id)
        referrer = await context.bot.get_chat(referrer_id) if referrer_id else None

        # Generate the admin notification message
        admin_message = generate_admin_message(user, user_id, referrer, referrer_id)

        # Send the message to the admin
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message)

        logging.info(f"Admin notified about new user ID: {user_id}")
    except Exception as e:
        logging.error(f"Failed to send admin notification for user ID {user_id}. Error: {e}")


def generate_admin_message(user, user_id, referrer, referrer_id):
    """
    Generate the message text for notifying the admin.
    """
    message = (
        f"🆕 New User Verified!\n\n"
        f"User Information:\n"
        f"• ID: {user_id}\n"
        f"• Username: @{user.username if user.username else 'None'}\n"
        f"• Name: {user.first_name} {user.last_name if user.last_name else ''}\n\n"
    )

    if referrer:
        message += (
            f"Referred by:\n"
            f"• ID: {referrer_id}\n"
            f"• Username: @{referrer.username if referrer.username else 'None'}\n"
            f"• Name: {referrer.first_name} {referrer.last_name if referrer.last_name else ''}"
        )
    else:
        message += "No referrer (direct join)"

    return message

# Add logging to debug referral and notification logic
async def process_pending_referral(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Processing pending referral for user_id: {user_id}")
    referrer_id = pending_referrals.get(user_id)
    if referrer_id:
        logging.info(f"Found referrer_id: {referrer_id} for user_id: {user_id}")

        # Check if this is not a self-referral and user hasn't been referred before
        if referrer_id != user_id and user_id not in get_referrals(referrer_id):
            # Add to referrals and credit bonus
            add_referral(referrer_id, user_id)
            update_user_balance(referrer_id, REFERRAL_BONUS)  # Ensure referral bonus is added
            logging.info(f"Referral bonus credited to referrer_id: {referrer_id}.")

            try:
                # Notify referrer
                await context.bot.send_message(
                    chat_id=referrer_id,
                    text=f"🎉 Your referral has been verified!\nYou earned ₦{REFERRAL_BONUS}!\nNew balance: ₦{get_user_balance(referrer_id)}"
                )

                # Notify new user
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ Verification complete! Your referrer earned ₦{REFERRAL_BONUS}!"
                )

                # Notify admin
                await notify_admin_new_user(user_id, {}, referrer_id, context)
            except Exception as e:
                logging.error(f"Error in referral notification: {e}")

        # Clean up pending referral
        pending_referrals.pop(user_id, None)
        logging.info(f"Pending referral for user_id: {user_id} has been processed and removed.")

async def check_and_handle_membership_change(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        logging.info(f"User {user_id}: Checking membership status")

        # Check channel membership
        try:
            channel_member = await context.bot.getChatMember(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        except Exception as e:
            logging.error(f"Error checking channel membership: {e}")
            await context.bot.send_message(
                chat_id=user_id,
                text=("❌ Unable to verify your channel membership. Please ensure you have joined the required channel. "
                      "If the issue persists, try again later.")
            )
            return False

        # Check group membership
        try:
            group_member = await context.bot.getChatMember(chat_id=GROUP_USERNAME, user_id=user_id)
        except Exception as e:
            logging.error(f"Error checking group membership: {e}")
            await context.bot.send_message(
                chat_id=user_id,
                text=("❌ Unable to verify your group membership. Please ensure you have joined the required group. "
                      "If the issue persists, try again later.")
            )
            return False

        valid_member_status = [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER
        ]

        is_verified = (
            channel_member.status in valid_member_status and
            group_member.status in valid_member_status
        )

        logging.info(f"User {user_id}: Membership verified: {is_verified}")

        user_verified_status[user_id] = is_verified

        if (is_verified):
            await process_pending_referral(user_id, context)
        else:
            await context.bot.send_message(
                chat_id=user_id,
                text=("❌ Verification failed. Please ensure you have joined both the required channel and group. "
                      "If you believe this is an error, contact support.")
            )

        return is_verified
    except Exception as e:
        logging.error(f"Unexpected error in check_and_handle_membership_change: {e}")
        await context.bot.send_message(
            chat_id=user_id,
            text=("❌ An unexpected error occurred during verification. Please try again later. "
                  "If the issue persists, contact support.")
        )
        return False

check_membership = check_and_handle_membership_change

# Provide channel and group buttons during verification if the user isn't in them
async def show_join_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show join message with channel and group buttons"""
    keyboard = [
        [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME}")],
        [InlineKeyboardButton("👥 Join Group", url=REQUIRED_GROUP)],
        [InlineKeyboardButton("✅ Check Membership", callback_data='check_membership')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = (
        "⚠️ You must join our channel and group to use this bot!\n\n"
        "1. Join our channel\n"
        "2. Join our group\n"
        "3. Click 'Check Membership' button"
    )

    # Handle both new messages and editing existing messages
    if isinstance(update, Update):
        if update.callback_query:
            await update.callback_query.message.edit_text(
                message_text,
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                message_text,
                reply_markup=reply_markup
            )
    else:
        await update.edit_text(
            message_text,
            reply_markup=reply_markup
        )

# Fix the issue where update.message is None in button-related functions
async def show_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE, show_back=False):
    """Show the main dashboard with enhanced and correct user bot details"""
    user = update.effective_user
    user_id = user.id

    # Fetch user details
    balance = get_user_balance(user_id)
    referral_count = len(get_referrals(user_id))

    # Construct the dashboard message
    dashboard_message = (
        f"👤 Welcome, {user.first_name} {user.last_name if user.last_name else ''}\n"
        f"───────────────\n"
        f"💰 Balance: ₦{balance}\n"
        f"👥 Referrals: {referral_count}\n"
        f"📅 Min. Withdrawal: ₦{MIN_WITHDRAWAL}\n\n"
        f"What would you like to do?"
    )

    # Define the dashboard buttons
    buttons = [
        [InlineKeyboardButton("💰 Check Balance", callback_data='balance')],
        [InlineKeyboardButton("👥 My Referrals", callback_data='my_referrals')],
        [InlineKeyboardButton("🏆 Top Referrals", callback_data='top_referrals')],
        [InlineKeyboardButton("🎁 Daily Bonus", callback_data='daily_bonus')],
        [InlineKeyboardButton("📋 Tasks", callback_data='tasks')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]

    if show_back:
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data='back_to_menu')])

    # Send the dashboard message
    await update.message.reply_text(
        dashboard_message,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_verify_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle verification button click"""
    query = update.callback_query
    user_id = query.from_user.id

    await query.answer("🔍 Checking membership status...")

    try:
        # Ensure query.message is not None
        if query.message:
            await query.message.edit_text(
                "⏳ Verifying your membership...\n"
                "Please wait a moment."
            )
        else:
            # Fallback to sending a new message if query.message is None
            await context.bot.send_message(
                chat_id=user_id,
                text="⏳ Verifying your membership...\nPlease wait a moment."
            )

        # Membership check
        is_member = await check_membership(user_id, context)
        if not is_member:
            # Verification failed
            keyboard = [
                [
                    InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME}"),
                    InlineKeyboardButton("👥 Join Group", url=REQUIRED_GROUP)
                ],
                [InlineKeyboardButton("🔄 Try Again", callback_data='check_membership')]
            ]
            if query.message:
                await query.message.edit_text(
                    "❌ Verification Failed!\n\n"
                    "Please make sure to:\n"
                    "1. Join our channel\n"
                    "2. Join our group\n"
                    "3. Stay in both\n\n"
                    "Then click 'Try Again'",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        "❌ Verification Failed!\n\n"
                        "Please make sure to:\n"
                        "1. Join our channel\n"
                        "2. Join our group\n"
                        "3. Stay in both\n\n"
                        "Then click 'Try Again'"
                    ),
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            return

        # Check if user is already verified to avoid duplicate welcome bonus
        is_verified = is_user_verified(user_id)

        if not is_verified:
            # Give welcome bonus to new users
            update_user_balance(user_id, WELCOME_BONUS)
            set_user_verified(user_id, True)  # Mark user as verified

            if query.message:
                await query.message.edit_text(
                    "✅ Verification Successful!\n\n"
                    f"🎁 You received ₦{WELCOME_BONUS} welcome bonus!\n"
                    "Loading your dashboard..."
                )
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        "✅ Verification Successful!\n\n"
                        f"🎁 You received ₦{WELCOME_BONUS} welcome bonus!\n"
                        "Loading your dashboard..."
                    )
                )

            # Process referral if exists
            referrer_id = pending_referrals.get(user_id)
            if referrer_id and referrer_id != user_id:  # Prevent self-referral
                # Add referral and credit bonus
                add_referral(referrer_id, user_id)
                update_user_balance(referrer_id, REFERRAL_BONUS)

                # Check and process milestone rewards
                ref_count = len(get_referrals(referrer_id))
                milestone_reward = process_milestone_reward(referrer_id, ref_count)

                # Notify referrer with combined message
                notification = (
                    f"🎉 You earned ₦{REFERRAL_BONUS} for referring a new user!"
                )
                if milestone_reward > 0:
                    notification += f"\n🎯 Bonus: ₦{milestone_reward} for reaching {ref_count} referrals milestone!"
                notification += f"\nNew balance: ₦{get_user_balance(referrer_id)}"

                try:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text=notification
                    )
                except Exception as e:
                    logging.error(f"Failed to notify referrer: {e}")

                # Remove from pending referrals
                pending_referrals.pop(user_id, None)

            # Notify admin about new user
            await notify_admin_new_user(user_id, {}, referrer_id if referrer_id else None, context)
        else:
            if query.message:
                await query.message.edit_text(
                    "✅ Verification Successful!\n"
                    "Loading your dashboard..."
                )
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        "✅ Verification Successful!\n"
                        "Loading your dashboard..."
                    )
                )

        # Show dashboard after verification
        await show_dashboard(update, context)

    except Exception as e:
        logging.error(f"Error in verification: {e}")
        if query.message:
            await query.message.edit_text(
                "❌ An error occurred during verification. Please try again later.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Try Again", callback_data='check_membership')]])
            )
        else:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "❌ An error occurred during verification. Please try again later."
                ),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Try Again", callback_data='check_membership')]])
            )
# User balance operations

def get_user_balance(user_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT balance FROM user_balances WHERE user_id = %s", (user_id,))
                result = cur.fetchone()
                return result['balance'] if result else 0
    except Exception as e:
        print(f"Error fetching balance for user {user_id}: {e}")
        return 0

def update_user_balance(user_id, amount):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO user_balances (user_id, balance) VALUES (%s, %s) "
                    "ON CONFLICT (user_id) DO UPDATE SET balance = user_balances.balance + %s",
                    (user_id, amount, amount)
                )
                conn.commit()
    except Exception as e:
        print(f"Error updating balance for user {user_id}: {e}")

# Referral operations

def add_referral(referrer_id, referred_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO referrals (referrer_id, referred_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (referrer_id, referred_id)
            )
            conn.commit()

def get_referrals(referrer_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT referred_id FROM referrals WHERE referrer_id = %s", (referrer_id,))
            return [row['referred_id'] for row in cur.fetchall()]

# User activity logging

def log_user_activity(user_id, activity):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO user_activities (user_id, activity) VALUES (%s, %s)",
                (user_id, activity)
            )
            conn.commit()

def get_bot_activities(user_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT activity, timestamp FROM user_activities WHERE user_id = %s ORDER BY timestamp DESC",
                (user_id,)
            )
            return cur.fetchall()

# --- Verification status DB helpers ---
def is_user_verified(user_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT verified FROM user_verification WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            return row and row['verified']

def set_user_verified(user_id, verified=True):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO user_verification (user_id, verified) VALUES (%s, %s) "
                "ON CONFLICT (user_id) DO UPDATE SET verified = %s",
                (user_id, verified, verified)
            )
            conn.commit()

# --- BANK DETAILS HELPERS ---
def save_user_bank(user_id, account_number, bank, account_name):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO user_bank (user_id, account_number, bank, account_name) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (user_id) DO UPDATE SET account_number=%s, bank=%s, account_name=%s",
                (user_id, account_number, bank, account_name, account_number, bank, account_name)
            )
            conn.commit()

def get_user_bank(user_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT account_number, bank, account_name FROM user_bank WHERE user_id = %s", (user_id,))
            return cur.fetchone()

# --- WITHDRAWAL TIME HELPERS ---
def can_withdraw_today(user_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT last_withdrawal FROM user_withdrawal_time WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            if not row or not row['last_withdrawal']:
                return True
            last_time = row['last_withdrawal']
            now = datetime.now()
            return (now - last_time).total_seconds() >= 86400

def set_withdrawal_time(user_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO user_withdrawal_time (user_id, last_withdrawal) VALUES (%s, %s) "
                "ON CONFLICT (user_id) DO UPDATE SET last_withdrawal = %s",
                (user_id, datetime.now(), datetime.now())
            )
            conn.commit()

# Update the start command to include language selection
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the start command"""
    user = update.effective_user
    args = context.args

    # Handle referral
    if args:
        try:
            referrer_id = int(args[0])
            if referrer_id != user.id:  # Prevent self-referral
                pending_referrals[user.id] = referrer_id
                logging.info(f"Stored pending referral: {referrer_id} -> {user.id}")
        except ValueError:
            logging.warning(f"Invalid referrer ID: {args[0]}")

    # Always show verification menu on /start
    await show_verification_menu(update, context)
    return

async def handle_verify_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle verification button click"""
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer("🔍 Checking membership status...")
    
    try:
        await query.message.edit_text(
            "⏳ Verifying your membership...\n"
            "Please wait a moment."
        )
        
        # Membership check
        is_member = await check_membership(user_id, context)
        if not is_member:
            # Verification failed
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

        # New user verification logic
        user_data = get_user_data(user_id)
        is_new_user = not user_data['is_verified']
        
        if is_new_user:
            # Update user status as verified
            user_data['is_verified'] = True
            
            # Credit welcome bonus
            update_user_balance(user_id, WELCOME_BONUS)
            await query.message.edit_text(
                "✅ Verification Successful!\n\n"
                f"🎁 You received ₦{WELCOME_BONUS} welcome bonus!\n"
                "Loading your dashboard..."
            )
            
            # Notify admin about the new user
            admin_message = (
                f"🆕 New User Verified!\n\n"
                f"User Information:\n"
                f"• ID: {user_id}\n"
                f"• Username: @{query.from_user.username or 'None'}\n"
                f"• Name: {query.from_user.first_name} {query.from_user.last_name or ''}\n\n"
                f"🎁 Welcome bonus of ₦{WELCOME_BONUS} credited!"
            )
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message)

        # Handle referrals
        referrer_id = pending_referrals.pop(user_id, None)
        if referrer_id:
            add_referral(referrer_id, user_id)
            update_user_balance(referrer_id, REFERRAL_BONUS)

            # Notify referrer about the referral bonus
            await context.bot.send_message(
                chat_id=referrer_id,
                text=f"🎉 You earned ₦{REFERRAL_BONUS} for referring a new user!\nNew balance: ₦{get_user_balance(referrer_id)}"
            )
            
            # Notify admin about the referral
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"👥 Referral Processed\n\n"
                    f"Referrer:\n"
                    f"• ID: {referrer_id}\n"
                    f"• New Referral: {query.from_user.first_name} (ID: {user_id})\n"
                    f"🎁 Referral bonus of ₦{REFERRAL_BONUS} credited to referrer!"
                )
            )

        # Load the user dashboard
        await show_dashboard(update, context)

    except Exception as e:
        logging.error(f"Error in verification: {e}")
        await query.message.edit_text(
            "❌ An error occurred during verification. Please try again later.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Try Again", callback_data='verify_membership')]])
        )

async def can_withdraw_today(user_id: int) -> bool:
    today = datetime.now().date()
    last_date = last_withdrawal.get(user_id)
    return last_date is None or last_date < today

async def verify_referrals_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Verify that all referrals are still members"""
    if not get_referrals(user_id):
        return True
        
    all_members = True
    not_in_channel = []
    
    for referred_id in get_referrals(user_id):
        is_member = await check_membership(referred_id, context)
        if not is_member:
            all_members = False
            not_in_channel.append(referred_id)
    
    return all_members, not_in_channel

async def handle_withdrawal_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the withdrawal process"""
    query = update.callback_query
    user_id = query.from_user.id
    
    # First check user's membership
    is_member = await check_membership(user_id, context)
    if not is_member:
        await query.message.edit_text(
            "❌ You must be a member of our channel and group to withdraw!\n"
            "Please join and try again.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
        )
        return ConversationHandler.END

    # Check minimum referrals requirement
    ref_count = len(get_referrals(user_id))
    if ref_count < 5:
        await query.message.edit_text(
            f"❌ You need at least 5 referrals to withdraw.\n"
            f"You currently have {ref_count} referrals.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
        )
        return ConversationHandler.END
    
    # Check balance first
    balance = get_user_balance(user_id)
    if balance < MIN_WITHDRAWAL:
        await query.message.edit_text(
            f"❌ You need at least {MIN_WITHDRAWAL} points (₦{MIN_WITHDRAWAL}) to withdraw.\n"
            f"Your current balance: {balance} points (₦{balance})",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
        )
        return ConversationHandler.END
    
    # Initialize withdrawal dictionary
    context.user_data['withdrawal'] = {}
    
    # Check if user has saved bank details
    if user_id in user_bank_info:
        saved_info = user_bank_info[user_id]
        keyboard = [
            [InlineKeyboardButton("✅ Use Saved Account", callback_data='use_saved_account')],
            [InlineKeyboardButton("📝 New Account", callback_data='new_account')],
            [InlineKeyboardButton("🔙 Cancel", callback_data='cancel_withdrawal')]
        ]
        await query.message.edit_text(
            f"Found saved bank details:\nBank: {saved_info['bank']}\nAccount: {saved_info['account_number']}\n\nWould you like to use this account?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ACCOUNT_NUMBER
    
    # No saved details, proceed with normal flow
    await query.message.edit_text(
        "Please enter your account number (10 digits):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data='cancel_withdrawal')]])
    )
    return ACCOUNT_NUMBER

async def handle_account_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle account number input"""
    user_id = update.effective_user.id
    account_number = update.message.text.strip()
    
    # Validate account number
    if not account_number.isdigit() or len(account_number) != 10:
        await update.message.reply_text(
            "❌ Invalid account number! Please enter a valid 10-digit account number.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data='cancel_withdrawal')]])
        )
        return ACCOUNT_NUMBER
    
    # Check for uniqueness
    if account_number in account_number_to_user and account_number_to_user[account_number] != user_id:
        await update.message.reply_text(
            "❌ This account number is already in use by another user!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data='cancel_withdrawal')]])
        )
        return ACCOUNT_NUMBER
    
    # Save account number
    context.user_data['withdrawal']['account_number'] = account_number
    account_number_to_user[account_number] = user_id
    
    # Create bank selection keyboard
    keyboard = []
    row = []
    for bank in BANKS:
        row.append(InlineKeyboardButton(bank, callback_data=f'bank_{bank}'))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Cancel", callback_data='cancel_withdrawal')])
    
    await update.message.reply_text(
        "Select your bank:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return BANK_NAME

async def handle_bank_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bank selection"""
    query = update.callback_query
    if not query:
        return BANK_NAME
    
    if query.data == 'cancel_withdrawal':
        return await cancel_withdrawal(update, context)
    
    bank = query.data.replace('bank_', '')
    if bank not in BANKS:
        await query.answer("❌ Invalid bank selection!")
        return BANK_NAME
    
    # Save bank selection
    context.user_data['withdrawal']['bank'] = bank
    
    await query.message.edit_text(
        "Enter your account name (as shown in your bank):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data='cancel_withdrawal')]])
    )
    return ACCOUNT_NAME

# --- BANK DETAILS: Always save to DB for future use ---
# In handle_account_name, after collecting account_name, save to DB
async def handle_account_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ...existing code...
    user_id = update.effective_user.id
    account_name = update.message.text.strip()
    if len(account_name) < 3:
        await update.message.reply_text(
            "❌ Invalid account name! Name must be at least 3 characters long.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data='cancel_withdrawal')]])
        )
        return ACCOUNT_NAME
    context.user_data['withdrawal']['account_name'] = account_name
    # Save bank details to DB for future use
    wd = context.user_data['withdrawal']
    save_user_bank(user_id, wd['account_number'], wd['bank'], account_name)
    # ...existing code...
    
    # Show amount selection
    balance = get_user_balance(user_id)
    keyboard = []
    amounts = [amount for amount in WITHDRAWAL_AMOUNTS if amount <= balance]
    row = []
    for amount in amounts:
        row.append(InlineKeyboardButton(f"₦{amount}", callback_data=f'amount_{amount}'))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Cancel", callback_data='cancel_withdrawal')])
    
    await update.message.reply_text(
        f"Select withdrawal amount:\nYour balance: ₦{balance}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return AMOUNT_SELECTION

async def handle_amount_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle amount selection"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if query.data == 'cancel_withdrawal':
        return await cancel_withdrawal(update, context)
    
    amount = int(query.data.replace('amount_', ''))
    withdrawal_data = context.user_data.get('withdrawal', {})
    
    # Save bank info for potential future use
    user_bank_info[user_id] = {
        'account_number': withdrawal_data['account_number'],
        'bank': withdrawal_data['bank'],
        'account_name': withdrawal_data['account_name']
    }
    
    # Verify amount
    balance = get_user_balance(user_id)
    if amount > balance:
        await query.message.edit_text(
            "❌ Insufficient balance for this withdrawal amount!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
        )
        return ConversationHandler.END
    
    # Process withdrawal and store withdrawal state
    update_user_balance(user_id, -amount)
    last_withdrawal[user_id] = datetime.now().date()
    
    # Store withdrawal state for potential refund
    user_withdrawal_state[user_id] = {
        'amount': amount,
        'account_number': withdrawal_data['account_number'],
        'bank': withdrawal_data['bank'],
        'account_name': withdrawal_data['account_name']
    }
    
    # Save amount and notify admin
    withdrawal_data['amount'] = amount
    await notify_withdrawal_request(user_id, amount, withdrawal_data, context)
    
    # Show confirmation
    await query.message.edit_text(
        f"✅ Withdrawal request successful!\n\n"
        f"Account Details:\n"
        f"Name: {withdrawal_data['account_name']}\n"
        f"Bank: {withdrawal_data['bank']}\n"
        f"Account Number: {withdrawal_data['account_number']}\n"
        f"Amount: ₦{amount}\n"
        f"Remaining balance: ₦{get_user_balance(user_id)}\n\n"
        f"Your payment will be processed within 24 hours!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
    )
    
    # Clear withdrawal data
    context.user_data.pop('withdrawal', None)
    return ConversationHandler.END

async def cancel_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the withdrawal process"""
    query = update.callback_query
    if query:
        await query.message.edit_text(
            "Withdrawal cancelled.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
        )
    else:
        await update.message.reply_text(
            "Withdrawal cancelled.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
        )
    
    # Clear withdrawal data
    context.user_data.pop('withdrawal', None)
    return ConversationHandler.END

async def notify_withdrawal_request(user_id: int, amount: int, account_info: dict, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = await context.bot.get_chat(user_id)
        
        admin_message = (
            f"💸 New Withdrawal Request!\n\n"
            f"User Information:\n"
            f"• ID: {user_id}\n"
            f"• Username: @{user.username if user.username else 'None'}\n"
            f"• Name: {user.first_name} {user.last_name if user.last_name else ''}\n\n"
            f"Withdrawal Details:\n"
            f"• Amount: ₦{amount}\n"
            f"• Account Name: {account_info['account_name']}\n"
            f"• Bank: {account_info['bank']}\n"
            f"• Account Number: {account_info['account_number']}\n\n"
            f"Use /paid {user_id} to mark as paid (send screenshot after)\n"
            f"Use /reject {user_id} to reject"
        )
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_message
        )
    except Exception as e:
        print(f"Failed to send withdrawal notification: {e}")

async def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

async def handle_paid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not await is_admin(user.id):
        await update.message.reply_text("❌ This command is only for admins!")
        return
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "❌ Usage: /paid <user_id>\n"
            "Please reply to this command with the payment screenshot!"
        )
        return
    
    try:
        target_user_id = int(context.args[0])
        
        # Store the target user ID for screenshot handling
        context.user_data['pending_payment_user'] = target_user_id
        
        await update.message.reply_text(
            "Please send the payment screenshot to confirm the payment."
        )
        return PAYMENT_SCREENSHOT
        
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID!")
        return

async def handle_payment_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment screenshot upload"""
    user = update.effective_user
    
    if not await is_admin(user.id):
        await update.message.reply_text("❌ This command is only for admins!")
        return ConversationHandler.END
    
    if not update.message.photo:
        await update.message.reply_text("❌ Please send a photo/screenshot!")
        return PAYMENT_SCREENSHOT
    
    target_user_id = context.user_data.get('pending_payment_user')
    if not target_user_id:
        await update.message.reply_text("❌ No pending payment to confirm!")
        return ConversationHandler.END
    
    try:
        target_user = await context.bot.get_chat(target_user_id)
        
        # Forward screenshot to user
        await context.bot.send_photo(
            chat_id=target_user_id,
            photo=update.message.photo[-1].file_id,
            caption="✅ Payment Confirmation\nYour withdrawal has been processed and paid!"
        )
        
        # Send payment notification to channel
        channel_message = (
            "💸 Payment Successfully Processed!\n\n"
            f"User: {target_user.first_name} {target_user.last_name if target_user.last_name else ''}\n"
            "Status: ✅ Paid\n\n"
            "💡 Join us and start earning:\n"
            f"https://t.me/{BOT_USERNAME}"
        )
        
        # Send to announcement channel
        await context.bot.send_photo(
            chat_id=ANNOUNCEMENT_CHANNEL,
            photo=update.message.photo[-1].file_id,
            caption=channel_message
        )
        
        # Clear pending payment
        del context.user_data['pending_payment_user']
        
        await update.message.reply_text(f"✅ Payment marked as completed for user {target_user_id}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    
    return ConversationHandler.END

async def handle_reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdrawal rejection by admin"""
    user = update.effective_user
    
    if not await is_admin(user.id):
        await update.message.reply_text("❌ This command is only for admins!")
        return
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("❌ Usage: /reject <user_id> [reason]")
        return
    
    try:
        target_user_id = int(context.args[0])
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
        
        # Refund the points if there's a pending withdrawal
        if target_user_id in user_withdrawal_state:
            withdrawal_info = user_withdrawal_state[target_user_id]
            refund_amount = withdrawal_info['amount']
            
            # Refund the points
            update_user_balance(target_user_id, refund_amount)
            
            # Notify user about rejection and refund
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(f"❌ Your withdrawal of ₦{refund_amount} has been rejected.\n"
                      f"Reason: {reason}\n\n"
                      f"✅ Your {refund_amount} points have been refunded to your balance.\n"
                      f"New balance: ₦{get_user_balance(target_user_id)}")
            )
            
            # Clear withdrawal state
            del user_withdrawal_state[target_user_id]
            
            await update.message.reply_text(
                f"✅ Rejected withdrawal for user {target_user_id}\n"
                f"Refunded ₦{refund_amount}"
            )
        else:
            await update.message.reply_text("❌ No pending withdrawal found for this user!")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def handle_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not await is_admin(user.id):
        await update.message.reply_text("❌ This command is only for admins!")
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("❌ Usage: /add <user_id> <amount>")
        return
    
    try:
        target_user_id = int(context.args[0])
        amount = int(context.args[1])
        
        if amount <= 0:
            await update.message.reply_text("❌ Amount must be positive!")
            return
        
        update_user_balance(target_user_id, amount)
        
        # Notify user
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"✨ {amount} points (₦{amount}) have been added to your balance by admin!"
        )
        
        await update.message.reply_text(
            f"✅ Added {amount} points to user {target_user_id}\n"
            f"New balance: {get_user_balance(target_user_id)} points"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def handle_deduct_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not await is_admin(user.id):
        await update.message.reply_text("❌ This command is only for admins!")
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("❌ Usage: /deduct <user_id> <amount>")
        return
    
    try:
        target_user_id = int(context.args[0])
        amount = int(context.args[1])
        
        if amount <= 0:
            await update.message.reply_text("❌ Amount must be positive!")
            return
        
        current_balance = get_user_balance(target_user_id)
        if current_balance < amount:
            await update.message.reply_text(
                f"❌ User only has {current_balance} points, cannot deduct {amount} points!"
            )
            return
        
        update_user_balance(target_user_id, -amount)
        
        # Notify user
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"📛 {amount} points (₦{amount}) have been deducted from your balance by admin."
        )
        
        await update.message.reply_text(
            f"✅ Deducted {amount} points from user {target_user_id}\n"
            f"New balance: {get_user_balance(target_user_id)} points"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

# Fix the /generate command to escape special characters properly
async def handle_generate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to generate a coupon code"""
    user = update.effective_user

    if not await is_admin(user.id):
        await update.message.reply_text("❌ This command is only for admins!")
        return

    if not context.args or len(context.args) < 1:
        await update.message.reply_text("❌ Usage: /generate <amount>")
        return

    try:
        amount = int(context.args[0])
        if amount <= 0:
            await update.message.reply_text("❌ Amount must be positive!")
            return

        code = generate_coupon_code()
        expiration_time = datetime.now() + timedelta(minutes=30)
        active_coupons[code] = {
            'amount': amount,
            'expires_at': expiration_time
        }
        used_coupons[code] = []

        # Properly escape the code for MarkdownV2
        escaped_code = escape_markdown(code, version=2)

        message = (
            f"✅ Generated new coupon code:\n\n"
            f"Code: {repr(escaped_code)}\n"
            f"Amount: ₦{amount}\n"
            f"Expires: {escape_markdown(expiration_time.strftime('%Y-%m-%d %H:%M:%S'), version=2)}\n\n"
            f"Users can redeem this code using:\n"
            f"/redeem {escaped_code}"
        )

        await update.message.reply_text(
            message,
            parse_mode='MarkdownV2'
        )
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid amount!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def handle_redeem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle coupon code redemption"""
    user = update.effective_user
    
    # Check if user is member of both channel and group
    is_member = await check_membership(user.id, context)
    if not is_member:
        await show_join_message(update, context)
        return
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "❌ Usage: /redeem <code>\n"
            "Example: /redeem ABC123"
        )
        return
    
    code = context.args[0].upper()
    
    if code not in active_coupons:
        await update.message.reply_text("❌ Invalid coupon code!")
        return
    
    coupon_data = active_coupons[code]
    current_time = datetime.now()
    
    # Check if coupon has expired
    if current_time > coupon_data['expires_at']:
        # Remove expired coupon
        del active_coupons[code]
        del used_coupons[code]
        await update.message.reply_text("❌ This coupon code has expired!")
        return
    
    if user.id in used_coupons[code]:
        await update.message.reply_text("❌ You have already used this coupon code!")
        return
    
    amount = coupon_data['amount']
    update_user_balance(user.id, amount)
    used_coupons[code].append(user.id)
    
    # Calculate remaining time
    time_remaining = coupon_data['expires_at'] - current_time
    minutes_remaining = int(time_remaining.total_seconds() / 60)
    
    await update.message.reply_text(
        f"🎉 Coupon code redeemed successfully!\n"
        f"Added ₦{amount} to your balance.\n"
        f"New balance: ₦{get_user_balance(user.id)}\n\n"
        f"Note: This code will expire in {minutes_remaining} minutes"
    )
    
    # Notify admin
    try:
        admin_message = (
            f"💫 Coupon Code Redeemed!\n\n"
            f"User Information:\n"
            f"• ID: {user.id}\n"
            f"• Username: @{user.username if user.username else 'None'}\n"
            f"• Name: {user.first_name} {user.last_name if user.last_name else ''}\n\n"
            f"Coupon Details:\n"
            f"• Code: {code}\n"
            f"• Amount: ₦{amount}\n"
            f"• Expires in: {minutes_remaining} minutes"
        )
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message)
    except Exception as e:
        print(f"Failed to send admin notification: {e}")

async def show_top_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show top referrals from database"""
    target_message = update.message or update.callback_query.message

    # Show loading animation
    await show_loading_animation(target_message, "Loading top referrers", 1)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT user_id, referral_count 
                    FROM top_referrals 
                    ORDER BY referral_count DESC 
                    LIMIT 5
                """)
                top_referrers = cur.fetchall()

        message = "🏆 Top 5 Referrers:\n\n"

        for i, referrer in enumerate(top_referrers, 1):
            try:
                user = await context.bot.get_chat(referrer['user_id'])
                username = f"@{user.username}" if user.username else f"User {referrer['user_id']}"
                message += f"{i}. {username} - {referrer['referral_count']} referrals\n"
            except Exception as e:
                message += f"{i}. User {referrer['user_id']} - {referrer['referral_count']} referrals\n"

        if not top_referrers:
            message += "No referrals yet!"

        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
        await target_message.edit_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logging.error(f"Error showing top referrals: {e}")
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
        await target_message.edit_text(
            "❌ Error loading top referrals. Please try again later.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# Add a function to clean expired coupons periodically
async def clean_expired_coupons():
    """Remove expired coupon codes"""
    current_time = datetime.now()
    expired_codes = [
        code for code, data in active_coupons.items()
        if current_time > data['expires_at']
    ]
    
    for code in expired_codes:
        del active_coupons[code]
        del used_coupons[code]

async def process_weekly_rewards(context: ContextTypes.DEFAULT_TYPE):
    """Process weekly rewards for top 2 referrers"""
    global last_weekly_reward
    current_time = datetime.now()

    # Check if a week has passed
    if (current_time - last_weekly_reward).days >= 7:
        # Get top 2 referrers with at least 30 referrals
        eligible_referrers = [(user_id, len(referred)) for user_id, referred in referrals.items() if len(referred) >= 30]
        top_referrers = sorted(eligible_referrers, key=lambda x: x[1], reverse=True)[:2]

        # Reward the top 2 referrers
        for i, (user_id, ref_count) in enumerate(top_referrers):
            reward = 1000 if i == 0 else 500  # 1st gets 1000, 2nd gets 500
            update_user_balance(user_id, reward)
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🎉 Congratulations! You're one of our top referrers this week!\n"
                         f"You earned ₦{reward} as a reward for having {ref_count} referrals!"
                )
            except Exception as e:
                print(f"Failed to send top referrer notification: {e}")

        # Announce in channel
        if top_referrers:
            try:
                message = "🏆 Weekly Top Referrers Awarded!\n\n"
                for i, (user_id, ref_count) in enumerate(top_referrers, start=1):
                    try:
                        user = await context.bot.get_chat(user_id)
                        name = user.first_name
                        message += f"{i}. {name}: {ref_count} referrals\n"
                    except:
                        message += f"{i}. User {user_id}: {ref_count} referrals\n"

                message += f"\n1st place: ₦1000\n2nd place: ₦500\n"

                await context.bot.send_message(
                    chat_id=ANNOUNCEMENT_CHANNEL,
                    text=message
                )
            except Exception as e:
                print(f"Failed to send channel announcement: {e}")

        last_weekly_reward = current_time

async def get_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get user information including referrals and balance"""
    user = update.effective_user

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get user balance and stats
                cur.execute("""
                    SELECT balance, total_earnings, referral_earnings, task_earnings
                    FROM user_balances 
                    WHERE user_id = %s
                """, (user.id,))
                user_data = cur.fetchone() or {'balance': 0, 'total_earnings': 0, 'referral_earnings': 0, 'task_earnings': 0}

                # Get referrals
                cur.execute("""
                    SELECT r.referred_id, u.username, u.first_name 
                    FROM referrals r 
                    LEFT JOIN user_info u ON r.referred_id = u.user_id 
                    WHERE r.referrer_id = %s
                """, (user.id,))
                referrals = cur.fetchall()

        info_message = (
            f"👤 Your Information\n"
            f"───────────────\n"
            f"ID: {user.id}\n"
            f"Balance: ₦{user_data['balance']:,}\n"
            f"Total Earnings: ₦{user_data['total_earnings']:,}\n"
            f"Referral Earnings: ₦{user_data['referral_earnings']:,}\n"
            f"Task Earnings: ₦{user_data['task_earnings']:,}\n"
            f"Total Referrals: {len(referrals)}\n"
            f"Min. Withdrawal: ₦{MIN_WITHDRAWAL}\n\n"
            f"Your Referrals:\n"
        )

        if referrals:
            for ref in referrals:
                name = ref['first_name'] or 'Unknown'
                username = ref['username'] or 'No username'
                info_message += f"• {name} (@{username})\n"
        else:
            info_message += "No referrals yet\n"

        await update.message.reply_text(info_message)
    except Exception as e:
        logging.error(f"Error fetching user information: {e}")
        await update.message.reply_text("❌ An error occurred while fetching user information. Please try again later.")

async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to get chat ID"""
    user = update.effective_user
    
    if not await is_admin(user.id):
        await update.message.reply_text("❌ This command is only for admins!")
        return
        
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"Current chat ID: {chat_id}")

# Update group chat reward system
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle group chat messages and reward group activity"""
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    chat = update.effective_chat

    # Only reward messages in group chats
    if (chat.type != "group" and chat.type != "supergroup"):
        return

    # Check membership first
    is_member = await check_membership(user.id, context)
    if not is_member:
        await show_join_message(update, context)
        return

    # Process group chat reward
    today = datetime.now().date()
    if chat.id not in last_chat_reward or last_chat_reward[chat.id] != today:
        # Reset daily counts if it's a new day
        last_chat_reward[chat.id] = today
        daily_chat_count[chat.id] = 0

    # Check if group hasn't reached daily chat reward limit
    if daily_chat_count[chat.id] < MAX_DAILY_CHAT_REWARD:
        daily_chat_count[chat.id] += 1
        for member_id in user_balances.keys():
            update_user_balance(member_id, CHAT_REWARD)
        await update.message.reply_text(
            f"💬 Thanks for being active in the group! Each member earned ₦{CHAT_REWARD}.\n"
            f"Today's group chat earnings: {daily_chat_count[chat.id]}/50."
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button clicks"""
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()  # Acknowledge the button click immediately

    # Handle verification check first
    if query.data == 'check_membership':
        is_member = await check_membership(user_id, context)
        if is_member:
            set_user_verified(user_id, True)
            await show_dashboard(update, context)
        else:
            await show_verification_menu(update, context)
        return

    # For all other buttons, verify membership first
    if not is_user_verified(user_id):
        await show_verification_menu(update, context)
        return

    # Handle other buttons only if verified
    if query.data == 'back_to_menu':
        await show_dashboard(update, context)
    elif query.data == 'my_referrals':
        await show_referral_menu(update, context)
    elif query.data == 'top_referrals':
        await show_top_referrals(update, context)
    elif query.data == 'daily_bonus':
        daily_bonus_earned = await check_and_credit_daily_bonus(user_id)
        if daily_bonus_earned:
            await query.message.edit_text(
                f"🎉 You have received your daily bonus of {DAILY_BONUS} points (₦{DAILY_BONUS})!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
            )
        else:
            await query.message.edit_text(
                "❌ You have already claimed your daily bonus today!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
            )
    elif query.data == 'balance':
        balance = get_user_balance(user_id)
        await query.message.edit_text(
            f"Your current balance: {balance} points (₦{balance}) 💰",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
        )
    elif query.data == 'tasks':
        await handle_tasks_button(update, context)
    elif query.data == 'quiz':
        await show_quiz_menu(update, context)
    elif query.data.startswith('quiz_'):
        await handle_quiz_answer(update, context)
    elif query.data == 'task_1':
        await handle_task_1_menu(update, context)
    elif query.data == 'task_2':
        await handle_task_2_menu(update, context)
    elif query.data == 'help':
        await show_help(update, context)
    elif query.data == 'show_history':
        await show_transaction_history(update, context)

async def handle_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle task submission with screenshot"""
    user = update.effective_user

    # Check membership
    is_member = await check_membership(user.id, context)
    if not is_member:
        await show_join_message(update, context)
        return

    # Check if command is replying to a message with photo
    reply_to_message = update.message.reply_to_message
    photo = None
    
    if (reply_to_message and reply_to_message.photo):
        # Use the photo from the replied message
        photo = reply_to_message.photo[-1]
    elif update.message.photo:
        # Use directly attached photo
        photo = update.message.photo[-1]
    
    if not photo:
        await update.message.reply_text(
            "❌ Please either:\n"
            "1. Attach a screenshot with the /task command, or\n"
            "2. Reply to a screenshot with the /task command"
        )
        return

    try:
        # Notify admin about the submission
        admin_message = (
            f"📝 New Task Submission!\n\n"
            f"From User:\n"
            f"• ID: {user.id}\n"
            f"• Username: @{user.username if user.username else 'None'}\n"
            f"• Name: {user.first_name} {user.last_name if user.last_name else ''}"
        )

        # Forward screenshot to admin
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=photo.file_id,
            caption=admin_message + f"\n\nUse /approve_task {user.id} to approve\nUse /reject_task {user.id} to reject"
        )

        await update.message.reply_text(
            "✅ Your task screenshot has been submitted for review!\n"
            "You will receive your reward once approved."
        )
    except Exception as e:
        await update.message.reply_text(
            "❌ Error submitting task. Please try again later."
        )

async def handle_task_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle task approval by admin"""
    user = update.effective_user
    
    if not await is_admin(user.id):
        await update.message.reply_text("❌ This command is only for admins!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Usage: /approve_task <user_id>")
        return
    
    try:
        target_user_id = int(context.args[0])
        
        # Add reward to user's balance
        update_user_balance(target_user_id, TASK_REWARD)
        
        # Notify user
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"🎉 Your task has been approved!\n"
                 f"Added ₦{TASK_REWARD} to your balance."
        )
        
        await update.message.reply_text(f"✅ Task approved for user {target_user_id}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def handle_task_rejection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle task rejection by admin"""
    user = update.effective_user
    
    if not await is_admin(user.id):
        await update.message.reply_text("❌ This command is only for admins!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Usage: /reject_task <user_id> [reason]")
        return
    
    try:
        target_user_id = int(context.args[0])
        reason = ' '.join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
        
        # Notify user
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"❌ Your task has been rejected.\n"
                 f"Reason: {reason}"
        )
        
        await update.message.reply_text(f"✅ Task rejected for user {target_user_id}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def handle_tasks_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle tasks button click and show task selection menu"""
    keyboard = [
        [InlineKeyboardButton("📱 Task 1: Referral Sharing", callback_data='task_1')],
        [InlineKeyboardButton("👥 Task 2: Join Group", callback_data='task_2')],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]
    ]
    
    await update.callback_query.message.edit_text(
        "📋 Available Tasks\n"
        "══════════════\n\n"
        "Choose a task to complete:\n\n"
        "1️⃣ Share your referral link\n"
        "2️⃣ Join our community group\n\n"
        "Select a task to view instructions!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_task_1_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show Task 1 instructions"""
    keyboard = [
        [InlineKeyboardButton("📤 Submit Screenshot", callback_data='submit_task_1')],
        [InlineKeyboardButton("🔙 Back to Tasks", callback_data='tasks')],
        [InlineKeyboardButton("🏠 Main Menu", callback_data='back_to_menu')]
    ]
    
    await update.callback_query.message.edit_text(
        "📱 Task 1: Share Referral Link\n"
        "═══════════════════════\n\n"
        "Instructions:\n"
        "1. Join our channel and group\n"
        "2. Share your referral link on any social media\n"
        "3. Take a screenshot showing:\n"
        "   • Your post with the referral link, OR\n"
        "   • Your content/review about our bot\n"
        "4. Send the screenshot using /task command\n\n"
        f"Reward: ₦{TASK_REWARD}\n\n"
        "Note: Your submission will be reviewed by admin",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_task_2_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show Task 2 instructions"""
    keyboard = [
        [InlineKeyboardButton("👥 Join Group", url="https://t.me/+qm80EPssXow4NTU1")],
        [InlineKeyboardButton("📤 Submit Screenshot", callback_data='submit_task_2')],
        [InlineKeyboardButton("🔙 Back to Tasks", callback_data='tasks')],
        [InlineKeyboardButton("🏠 Main Menu", callback_data='back_to_menu')]
    ]
    
    await update.callback_query.message.edit_text(
        "👥 Task 2: Join Our Community\n"
        "═══════════════════════\n\n"
        "Instructions:\n"
        "1. Join our community group using the button below\n"
        "2. Take a screenshot showing that you've joined\n"
        "3. Send the screenshot using /task command\n\n"
        f"Reward: ₦{TASK_REWARD}\n\n"
        "Note: Your submission will be reviewed by admin",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def notify_admin_verified_user(user_id: int, referrer_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Notify admin about new verified user"""
    try:
        user = await context.bot.get_chat(user_id)
        referrer = await context.bot.get_chat(referrer_id) if referrer_id else None
        
        admin_message = (
            "🆕 New User Verified!\n\n"
            f"👤 New User:\n"
            f"• ID: {user_id}\n"
            f"• Name: {user.first_name} {user.last_name if user.last_name else ''}\n"
            f"• Username: @{user.username if user.username else 'None'}\n\n"
        )
        
        if referrer:
            admin_message += (
                f"👥 Referred By:\n"
                f"• ID: {referrer_id}\n"
                f"• Name: {referrer.first_name} {referrer.last_name if referrer.last_name else ''}\n"
                f"• Username: @{referrer.username if referrer.username else 'None'}\n"
                f"• Total Referrals: {len(get_referrals(referrer_id))}"
            )
        else:
            admin_message += "Direct Join (No Referrer)"
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_message
        )
    except Exception as e:
        print(f"Failed to send admin notification: {e}")

# Expand quiz data to 50 harder and clearer questions
quiz_data = [
    {"question": "What year did the Titanic sink?", "options": ["1912", "1905", "1920"], "answer": "1912"},
    {"question": "Who painted the Mona Lisa?", "options": ["Leonardo da Vinci", "Pablo Picasso", "Vincent van Gogh"], "answer": "Leonardo da Vinci"},
    {"question": "What is the smallest planet in our solar system?", "options": ["Mercury", "Mars", "Venus"], "answer": "Mercury"},
    {"question": "Which country won the FIFA World Cup in 2018?", "options": ["France", "Croatia", "Germany"], "answer": "France"},
    {"question": "What is the capital of Australia?", "options": ["Canberra", "Sydney", "Melbourne"], "answer": "Canberra"},
    {"question": "Who discovered penicillin?", "options": ["Alexander Fleming", "Marie Curie", "Louis Pasteur"], "answer": "Alexander Fleming"},
    {"question": "What is the largest desert in the world?", "options": ["Sahara", "Antarctica", "Gobi"], "answer": "Antarctica"},
    {"question": "Which year did World War II end?", "options": ["1945", "1939", "1950"], "answer": "1945"},
    {"question": "Who wrote 'To Kill a Mockingbird'?", "options": ["Harper Lee", "Mark Twain", "Ernest Hemingway"], "answer": "Harper Lee"},
    {"question": "What is the chemical symbol for gold?", "options": ["Au", "Ag", "Pb"], "answer": "Au"},
    {"question": "What is the longest river in the world?", "options": ["Nile", "Amazon", "Yangtze"], "answer": "Nile"},
    {"question": "Who was the first man to step on the moon?", "options": ["Neil Armstrong", "Buzz Aldrin", "Yuri Gagarin"], "answer": "Neil Armstrong"},
    {"question": "What is the capital of Japan?", "options": ["Tokyo", "Kyoto", "Osaka"], "answer": "Tokyo"},
    {"question": "Which element has the chemical symbol 'O'?", "options": ["Oxygen", "Osmium", "Oganesson"], "answer": "Oxygen"},
    {"question": "What is the largest mammal in the world?", "options": ["Blue Whale", "Elephant", "Giraffe"], "answer": "Blue Whale"},
    {"question": "Who is known as the father of computers?", "options": ["Charles Babbage", "Alan Turing", "John von Neumann"], "answer": "Charles Babbage"},
    {"question": "What is the capital of Egypt?", "options": ["Cairo", "Alexandria", "Giza"], "answer": "Cairo"},
    {"question": "Which planet is known as the Red Planet?", "options": ["Mars", "Jupiter", "Saturn"], "answer": "Mars"},
    {"question": "Who wrote 'Romeo and Juliet'?", "options": ["William Shakespeare", "Charles Dickens", "Jane Austen"], "answer": "William Shakespeare"},
    {"question": "What is the boiling point of water at sea level?", "options": ["100°C", "90°C", "110°C"], "answer": "100°C"},
    {"question": "Which country is known as the Land of the Rising Sun?", "options": ["Japan", "China", "South Korea"], "answer": "Japan"},
    {"question": "What is the largest ocean on Earth?", "options": ["Pacific Ocean", "Atlantic Ocean", "Indian Ocean"], "answer": "Pacific Ocean"},
    {"question": "Who invented the telephone?", "options": ["Alexander Graham Bell", "Thomas Edison", "Nikola Tesla"], "answer": "Alexander Graham Bell"},
    {"question": "What is the capital of France?", "options": ["Paris", "Lyon", "Marseille"], "answer": "Paris"},
    {"question": "Which gas do plants use for photosynthesis?", "options": ["Carbon Dioxide", "Oxygen", "Nitrogen"], "answer": "Carbon Dioxide"},
    {"question": "Who painted the ceiling of the Sistine Chapel?", "options": ["Michelangelo", "Raphael", "Leonardo da Vinci"], "answer": "Michelangelo"},
    {"question": "What is the capital of the United States?", "options": ["Washington, D.C.", "New York", "Los Angeles"], "answer": "Washington, D.C."},
    {"question": "Which planet is closest to the Sun?", "options": ["Mercury", "Venus", "Earth"], "answer": "Mercury"},
    {"question": "Who discovered gravity?", "options": ["Isaac Newton", "Albert Einstein", "Galileo Galilei"], "answer": "Isaac Newton"},
    {"question": "What is the capital of Germany?", "options": ["Berlin", "Munich", "Frankfurt"], "answer": "Berlin"},
    {"question": "Which is the largest continent?", "options": ["Asia", "Africa", "Europe"], "answer": "Asia"},
    {"question": "Who wrote 'Pride and Prejudice'?", "options": ["Jane Austen", "Charlotte Bronte", "Emily Bronte"], "answer": "Jane Austen"},
    {"question": "What is the chemical symbol for water?", "options": ["H2O", "O2", "CO2"], "answer": "H2O"},
    {"question": "Which country is known for the Great Wall?", "options": ["China", "India", "Japan"], "answer": "China"},
    {"question": "What is the capital of Canada?", "options": ["Ottawa", "Toronto", "Vancouver"], "answer": "Ottawa"},
    {"question": "Who developed the theory of relativity?", "options": ["Albert Einstein", "Isaac Newton", "Niels Bohr"], "answer": "Albert Einstein"},
    {"question": "What is the largest island in the world?", "options": ["Greenland", "Australia", "Madagascar"], "answer": "Greenland"},
    {"question": "Which year did the Berlin Wall fall?", "options": ["1989", "1990", "1988"], "answer": "1989"},
    {"question": "What is the capital of Italy?", "options": ["Rome", "Milan", "Naples"], "answer": "Rome"},
    {"question": "Which is the smallest country in the world?", "options": ["Vatican City", "Monaco", "San Marino"], "answer": "Vatican City"},
    {"question": "Who wrote 'The Odyssey'?", "options": ["Homer", "Virgil", "Sophocles"], "answer": "Homer"},
    {"question": "What is the speed of light?", "options": ["299,792 km/s", "300,000 km/s", "150,000 km/s"], "answer": "299,792 km/s"},
    {"question": "Which country is known for the Eiffel Tower?", "options": ["France", "Italy", "Germany"], "answer": "France"},
    {"question": "What is the capital of Russia?", "options": ["Moscow", "Saint Petersburg", "Kazan"], "answer": "Moscow"},
    {"question": "Who discovered America?", "options": ["Christopher Columbus", "Ferdinand Magellan", "James Cook"], "answer": "Christopher Columbus"},
    {"question": "What is the largest organ in the human body?", "options": ["Skin", "Liver", "Heart"], "answer": "Skin"},
    {"question": "Which year did the first manned moon landing occur?", "options": ["1969", "1970", "1968"], "answer": "1969"},
    {"question": "What is the capital of South Africa?", "options": ["Pretoria", "Cape Town", "Johannesburg"], "answer": "Pretoria"},
    {"question": "Who wrote '1984'?", "options": ["George Orwell", "Aldous Huxley", "Ray Bradbury"], "answer": "George Orwell"}
]

# Remove language support
# ...existing code...
# Remove language-related handlers and functions
# ...existing code...

# Update quiz retry logic to use a 10-second timer
import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

async def show_quiz_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show quiz menu with a random question and a 10-second timer."""
    user_id = update.effective_user.id
    today = datetime.now().date()

    # Check if user has already taken the quiz today
    if user_id in user_quiz_status and user_quiz_status[user_id] == today:
        await update.callback_query.message.edit_text(
            "❌ You have already taken the quiz today! Come back tomorrow for another chance.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
        )
        return

    # Select a random quiz question
    quiz = random.choice(quiz_data)
    question = quiz["question"]
    options = quiz["options"]
    correct_answer = quiz["answer"]

    # Save the correct answer and quiz status in context
    context.user_data['quiz_answer'] = correct_answer
    context.user_data['quiz_active'] = True

    # Create buttons for options
    keyboard = [[InlineKeyboardButton(option, callback_data=f'quiz_{option}')] for option in options]
    keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')])

    # Show the question
    question_message = await update.callback_query.message.edit_text(
        f"📝 Quiz Question:\n\n{question}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    # Start 10-second timer
    try:
        await asyncio.sleep(10)

        # Check if the quiz is still active (i.e., no answer was provided)
        if context.user_data.get('quiz_active', False):
            context.user_data['quiz_active'] = False  # Mark quiz as inactive
            await context.bot.edit_message_text(
                chat_id=question_message.chat_id,
                message_id=question_message.message_id,
                text=f"⏰ Time's up! The correct answer was: {correct_answer}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
            )
    except Exception as e:
        print(f"Error during quiz timer: {e}")

# Update referral milestones to start from 50
MILESTONES = [50, 100, 200]  # Define referral milestones

async def check_milestones(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Check if the user has reached a referral milestone"""
    ref_count = len(get_referrals(user_id))
    for milestone in MILESTONES:
        if ref_count == milestone:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎉 Congratulations! You've reached {milestone} referrals and earned a special reward!"
            )
            # Add a reward for reaching the milestone
            update_user_balance(user_id, 1000)  # Example reward
            break

# Add transaction history
transaction_history = {}  # Format: {user_id: [{'type': 'credit', 'amount': 50, 'date': '2025-04-10'}]}

def log_transaction(user_id: int, transaction_type: str, amount: int):
    """Log a transaction for a user"""
    if user_id not in transaction_history:
        transaction_history[user_id] = []
    transaction_history[user_id].append({
        'type': transaction_type,
        'amount': amount,
        'date': datetime.now().strftime('%Y-%m-%d')
    })

async def show_transaction_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the user's earning and withdrawal history"""
    user_id = update.effective_user.id

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Fetch earnings history
                cur.execute("""
                    SELECT activity, amount, timestamp 
                    FROM user_activities 
                    WHERE user_id = %s AND activity LIKE '%earning%'
                    ORDER BY timestamp DESC
                    LIMIT 10
                """, (user_id,))
                earnings = cur.fetchall()

                # Fetch withdrawal history
                cur.execute("""
                    SELECT activity, amount, timestamp 
                    FROM user_activities 
                    WHERE user_id = %s AND activity LIKE '%withdrawal%'
                    ORDER BY timestamp DESC
                    LIMIT 10
                """, (user_id,))
                withdrawals = cur.fetchall()

        message = "📜 Your Transaction History\n\n"

        message += "💰 Recent Earnings:\n"
        if earnings:
            for earning in earnings:
                date = earning['timestamp'].strftime("%Y-%m-%d")
                message += f"• {date}: +₦{earning['amount']} ({earning['activity']})\n"
        else:
            message += "No recent earnings\n"

        message += "\n💸 Recent Withdrawals:\n"
        if withdrawals:
            for withdrawal in withdrawals:
                date = withdrawal['timestamp'].strftime("%Y-%m-%d")
                message += f"• {date}: -₦{withdrawal['amount']} ({withdrawal['activity']})\n"
        else:
            message += "No recent withdrawals\n"

        await update.message.reply_text(message)
    except Exception as e:
        logging.error(f"Error fetching transaction history: {e}")
        await update.message.reply_text("❌ Error fetching history. Please try again later.")

# Add admin dashboard
async def admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show comprehensive admin dashboard"""
    user = update.effective_user
    
    if not await is_admin(user.id):
        await update.message.reply_text("❌ This command is only for admins!")
        return

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get total users
                cur.execute("SELECT COUNT(DISTINCT user_id) FROM user_balances")
                total_users = cur.fetchone()['count']

                # Get total referrals
                cur.execute("SELECT COUNT(*) FROM referrals")
                total_referrals = cur.fetchone()['count']

                # Get total balance
                cur.execute("SELECT SUM(balance) FROM user_balances")
                total_balance = cur.fetchone()['sum'] or 0

                # Get users with pending withdrawals
                cur.execute("SELECT COUNT(*) FROM user_activities WHERE activity LIKE 'withdrawal_pending%'")
                pending_withdrawals = cur.fetchone()['count']

                # Get total withdrawn
                cur.execute("SELECT COUNT(*) FROM user_activities WHERE activity LIKE 'withdrawal_completed%'")
                completed_withdrawals = cur.fetchone()['count']

                # Get active users today
                today = datetime.now().date()
                cur.execute("SELECT COUNT(DISTINCT user_id) FROM user_activities WHERE DATE(timestamp) = %s", (today,))
                active_today = cur.fetchone()['count']

        dashboard = (
            "📊 Admin Dashboard\n"
            "═══════════════\n\n"
            f"👥 Users\n"
            f"• Total Users: {total_users}\n"
            f"• Active Today: {active_today}\n\n"
            f"💰 Finance\n"
            f"• Total Balance: ₦{total_balance}\n"
            f"• Pending Withdrawals: {pending_withdrawals}\n"
            f"• Completed Withdrawals: {completed_withdrawals}\n\n"
            f"📈 Referrals\n"
            f"• Total Referrals: {total_referrals}\n"
            f"• Avg. Referrals/User: {total_referrals/total_users:.2f}\n\n"
            f"Use /info <user_id> to check specific user details"
        )

        await update.message.reply_text(dashboard)
    except Exception as e:
        await update.message.reply_text(f"❌ Error fetching dashboard data: {str(e)}")

# Define periodic_tasks function
async def periodic_tasks(context: ContextTypes.DEFAULT_TYPE):
    """Run periodic tasks like inactivity and referral checks"""
    await check_inactivity()
    await handle_referral_membership_changes(context)

async def check_inactivity():
    """Check for inactive users and take appropriate actions."""
    inactive_users = []
    current_time = datetime.now()

    for user_id, last_active in last_signin.items():
        # Consider users inactive if they haven't signed in for 30 days
        if (current_time - last_active).days > 30:
            inactive_users.append(user_id)

    for user_id in inactive_users:
        # Remove inactive users from referrals and balances
        referrals.pop(user_id, None)
        user_balances.pop(user_id, None)
        print(f"Removed inactive user: {user_id}")

async def handle_referral_membership_changes(context: ContextTypes.DEFAULT_TYPE):
    """Deduct balance if a referral leaves the channel or group."""
    for referrer_id, referred_users in referrals.items():
        for referred_id in list(referred_users):
            is_member = await check_membership(referred_id, context)
            if not is_member:
                # Deduct balance from referrer
                update_user_balance(referrer_id, -LEAVE_PENALTY)

                # Notify referrer about the deduction
                try:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text=(f"⚠️ One of your referrals left the group or channel."
                              f" A penalty of ₦{LEAVE_PENALTY} has been deducted from your balance.")
                    )
                except Exception as e:
                    print(f"Failed to notify referrer {referrer_id}: {e}")

                # Remove the referral
                referred_users.remove(referred_id)
                print(f"Removed referral {referred_id} for referrer {referrer_id}")

async def log_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Received update: {update}")

# Database connection setup
DATABASE_URL = "postgres://u3krleih91oqbi:pcd8f6341baeb90af4a8c9cd122e720c6372449c90ba90d5df39a39e0b954c562@c9pv5s2sq0i76o.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com:5432/d5ac9cb5iuidbo"
def get_db_connection():
    db_url = os.getenv("DATABASE_URL", "postgres://u3krleih91oqbi:pcd8f6341baeb90af4a8c9cd122e720c6372449c90ba90d5df39a39e0b954c562@c9pv5s2sq0i76o.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com:5432/d5ac9cb5iuidbo")
    result = urlparse(db_url)

    return psycopg2.connect(
        dbname=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port,
        cursor_factory=RealDictCursor
    )

# Save bot activity to the database
def save_bot_activity(user_id, activity):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bot_activities (user_id, activity, timestamp)
                VALUES (%s, %s, NOW())
                """,
                (user_id, activity)
            )
            conn.commit()

# Retrieve bot activities for a user
def get_bot_activities(user_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT activity, timestamp
                FROM bot_activities
                WHERE user_id = %s
                ORDER BY timestamp DESC
                """,
                (user_id,)
            )
            return cur.fetchall()

# Example usage
# save_bot_activity('user123', 'Checked balance')
# activities = get_bot_activities('user123')
# print(activities)

import psycopg2
from psycopg2.extras import RealDictCursor
from urllib.parse import urlparse

# Update database connection setup to use the provided URL
def get_db_connection():
    db_url = os.getenv("DATABASE_URL", "postgres://u3krleih91oqbi:pcd8f6341baeb90af4a8c9cd122e720c6372449c90ba90d5df39a39e0b954c562@c9pv5s2sq0i76o.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com:5432/d5ac9cb5iuidbo")
    result = urlparse(db_url)

    return psycopg2.connect(
        dbname=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port,
        cursor_factory=RealDictCursor
    )

# Replace in-memory user_balances with database operations
def get_user_balance(user_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT balance FROM user_balances WHERE user_id = %s", (user_id,))
            result = cur.fetchone()
            return result['balance'] if result else 0

def update_user_balance(user_id, amount):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO user_balances (user_id, balance) VALUES (%s, %s) "
                "ON CONFLICT (user_id) DO UPDATE SET balance = user_balances.balance + %s",
                (user_id, amount, amount)
            )
            conn.commit()

# Replace in-memory referrals with database operations
def add_referral(referrer_id, referred_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO referrals (referrer_id, referred_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (referrer_id, referred_id)
            )
            conn.commit()

def get_referrals(referrer_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT referred_id FROM referrals WHERE referrer_id = %s", (referrer_id,))
            return [row['referred_id'] for row in cur.fetchall()]

# Example: Update the /start command to use the database
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Extract referrer ID from the start parameter
    args = context.args
    if args:
        try:
            referrer_id = int(args[0])
            if referrer_id != user.id:  # Prevent self-referral
                add_referral(referrer_id, user.id)
        except ValueError:
            logging.warning(f"Invalid referrer ID in /start command: {args[0]}")

    # Get user balance from the database
    balance = get_user_balance(user.id)

    # Show dashboard
    await show_verification_menu(update, context)
    return
# Ensure database tables exist
def initialize_database():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Create user_balances table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS user_balances (
                        user_id BIGINT PRIMARY KEY,
                        balance FLOAT DEFAULT 0
                    );
                """)

                # Create referrals table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS referrals (
                        referrer_id BIGINT REFERENCES user_balances(user_id),
                        referred_id BIGINT REFERENCES user_balances(user_id),
                        PRIMARY KEY (referrer_id, referred_id)
                    );
                """)

                # Create task_earnings table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS task_earnings (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL REFERENCES user_balances(user_id),
                        amount FLOAT NOT NULL,
                        earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)

                conn.commit()
    except Exception as e:
        print(f"Error initializing database: {e}")

# Periodic saving interval in seconds
SAVE_INTERVAL = 300  # Save every 5 minutes

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log the error and send a telegram message to notify the developer."""
    logging.error(msg="Exception while handling an update:", exc_info=context.error)
    
    # Send error message to admin
    error_message = f"❌ An error occurred: {context.error}"
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID, 
            text=error_message
        )
    except:
        logging.error("Failed to send error message to admin")

async def handle_quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quiz answer submissions"""
    query = update.callback_query
    user_id = query.from_user.id
    selected_option = query.data.replace('quiz_', '')

    # Check if quiz is still active
    if not context.user_data.get('quiz_active', False):
        await query.answer("❌ Quiz time expired! Try again tomorrow.")
        return

    # Get the correct answer
    correct_answer = context.user_data.get('quiz_answer')
    if not correct_answer:
        await query.answer("❌ Something went wrong. Please try again later.")
        return

    # Mark quiz as completed for today
    user_quiz_status[user_id] = datetime.now().date()
    context.user_data['quiz_active'] = False

    if selected_option == correct_answer:
        # Reward the user
        update_user_balance(user_id, 50)
        await query.message.edit_text(
            f"✅ Correct! You have earned ₦50.\nYour new balance is ₦{get_user_balance(user_id)}.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
        )
    else:
        await query.message.edit_text(
            f"❌ Wrong answer! The correct answer was: {correct_answer}. Try again tomorrow!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
        )
async def handle_del_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete user account and data from database"""
    user = update.effective_user

    if not await is_admin(user.id):
        if len(context.args) > 0:
            await update.message.reply_text("❌ Only admins can delete other users!")
            return

        # Allow users to delete their own account
        user_id = user.id
    else:
        # Admin can delete any account
        if not context.args:
            await update.message.reply_text("❌ Usage: /del <user_id>")
            return
        try:
            user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID!")
            return

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Delete from all related tables
                cur.execute("DELETE FROM user_balances WHERE user_id = %s", (user_id,))
                cur.execute("DELETE FROM referrals WHERE referrer_id = %s OR referred_id = %s", (user_id, user_id))
                cur.execute("DELETE FROM user_verification WHERE user_id = %s", (user_id,))
                cur.execute("DELETE FROM user_bank WHERE user_id = %s", (user_id,))
                cur.execute("DELETE FROM user_withdrawal_time WHERE user_id = %s", (user_id,))
                cur.execute("DELETE FROM user_activities WHERE user_id = %s", (user_id,))
                conn.commit()

                if await is_admin(user.id):
                    await update.message.reply_text(f"✅ Successfully deleted user {user_id} from database!")
                else:
                    await update.message.reply_text("✅ Your account has been deleted. Use /start to create a new account.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error deleting user: {str(e)}")
async def show_verification_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show verification menu with channel and group join buttons"""
    try:
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME}")],
            [InlineKeyboardButton("👥 Join Group", url=REQUIRED_GROUP)],
            [InlineKeyboardButton("✅ Check Membership", callback_data='check_membership')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = (
            "🔒 Please join our channel and group to use this bot!\n\n"
            "1. Join our channel\n"
            "2. Join our group\n"
            "3. Click 'Check Membership' button"
        )

        # Handle both new messages and callback queries
        if update.message:
            await update.message.reply_text(message_text, reply_markup=reply_markup)
        elif update.callback_query:
            await update.callback_query.message.edit_text(message_text, reply_markup=reply_markup)
    except Exception as e:
        logging.error(f"Error in show_verification_menu: {e}")
        # Handle error gracefully
        if update.callback_query:
            await update.callback_query.answer("An error occurred. Please try /start again.")
# Add back user_quiz_status for quiz tracking
user_quiz_status = {}

# Add back show_verification_menu for verification step
async def show_verification_menu(update, context):
    keyboard = [[InlineKeyboardButton("✅ Verify Membership", callback_data='verify_membership')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🔒 Please verify your membership by joining our channel and group before using the bot.",
        reply_markup=reply_markup
    )

# After the imports and before other code
# Add all status tracking variables
user_quiz_status = {}
user_verification_state = {}  # Track verification state

# After other existing functions
async def show_verification_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show verification menu with channel and group join buttons"""
    keyboard = [
        [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME}")],
        [InlineKeyboardButton("👥 Join Group", url=REQUIRED_GROUP)],
        [InlineKeyboardButton("✅ Verify Membership", callback_data='verify_membership')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(
            "🔒 Please join our channel and group to use this bot!\n\n"
            "1. Click the buttons below to join\n"
            "2. After joining, click 'Verify Membership'\n"
            "3. You'll receive your welcome bonus after verification!",
            reply_markup=reply_markup
        )
    elif update.callback_query:
        await update.callback_query.message.edit_text(
            "🔒 Please join our channel and group to use this bot!\n\n"
            "1. Click the buttons below to join\n"
            "2. After joining, click 'Verify Membership'\n"
            "3. You'll receive your welcome bonus after verification!",
            reply_markup=reply_markup
        )

# Add error handler function
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log the error and send a telegram message to notify the developer."""
    logging.error(msg="Exception while handling an update:", exc_info=context.error)
    
    # Send error message to admin
    error_message = f"❌ An error occurred: {context.error}"
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID, 
            text=error_message
        )
    except:
        pass

async def handle_quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quiz answer submissions"""
    query = update.callback_query
    user_id = query.from_user.id
    selected_option = query.data.replace('quiz_', '')

    # Check if quiz is still active
    if not context.user_data.get('quiz_active', False):
        await query.answer("❌ Quiz time expired! Try again tomorrow.")
        return

    # Get the correct answer
    correct_answer = context.user_data.get('quiz_answer')
    if not correct_answer:
        await query.answer("❌ Something went wrong. Please try again later.")
        return

    # Mark quiz as completed for today
    user_quiz_status[user_id] = datetime.now().date()
    context.user_data['quiz_active'] = False

    if selected_option == correct_answer:
        # Reward the user
        update_user_balance(user_id, 50)
        await query.message.edit_text(
            f"✅ Correct! You have earned ₦50.\nYour new balance is ₦{get_user_balance(user_id)}.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
        )
    else:
        await query.message.edit_text(
            f"❌ Wrong answer! The correct answer was: {correct_answer}. Try again tomorrow!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
        )

# Define the show_verification_menu function near the top of the file
async def show_verification_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show verification menu with channel and group join buttons"""
    keyboard = [
        [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME}")],
        [InlineKeyboardButton("👥 Join Group", url=REQUIRED_GROUP)],
        [InlineKeyboardButton("✅ Check Membership", callback_data='check_membership')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message_text = (
        "🔒 Please join our channel and group to use this bot!\n\n"
        "1. Click the buttons below to join\n"
        "2. After joining, click 'Check Membership'\n"
        "3. You'll receive your welcome bonus after verification!"
    )

    if update.message:
        await update.message.reply_text(message_text, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.edit_text(message_text, reply_markup=reply_markup)

# Update the /start command to use the show_verification_menu function
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the start command"""
    user = update.effective_user
    args = context.args

    # Handle referral
    if args:
        try:
            referrer_id = int(args[0])
            if referrer_id != user.id:  # Prevent self-referral
                pending_referrals[user.id] = referrer_id
                logging.info(f"Stored pending referral: {referrer_id} -> {user.id}")
        except ValueError:
            logging.warning(f"Invalid referrer ID: {args[0]}")

    # Always show verification menu on /start
    await show_verification_menu(update, context)
    return

async def show_verification_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show verification menu with channel and group join buttons"""
    try:
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME}")],
            [InlineKeyboardButton("👥 Join Group", url=REQUIRED_GROUP)],
            [InlineKeyboardButton("✅ Check Membership", callback_data='check_membership')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = (
            "🔒 Please join our channel and group to use this bot!\n\n"
            "1. Join our channel\n"
            "2. Join our group\n"
            "3. Click 'Check Membership' button"
        )

        # Handle both new messages and callback queries
        if update.message:
            await update.message.reply_text(message_text, reply_markup=reply_markup)
        elif update.callback_query:
            await update.callback_query.message.edit_text(message_text, reply_markup=reply_markup)
    except Exception as e:
        logging.error(f"Error in show_verification_menu: {e}")
        # Handle error gracefully
        if update.callback_query:
            await update.callback_query.answer("An error occurred. Please try /start again.")
async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's earning and withdrawal history"""
    user_id = update.effective_user.id
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get earnings history
                cur.execute("""
                    SELECT activity, amount, timestamp 
                    FROM user_activities 
                    WHERE user_id = %s AND activity LIKE '%earning%'
                    ORDER BY timestamp DESC
                    LIMIT 10
                """, (user_id,))
                earnings = cur.fetchall()
                
                # Get withdrawal history
                cur.execute("""
                    SELECT activity, amount, timestamp 
                    FROM user_activities 
                    WHERE user_id = %s AND activity LIKE '%withdrawal%'
                    ORDER BY timestamp DESC
                    LIMIT 10
                """, (user_id,))
                withdrawals = cur.fetchall()
        
        # Format message
        message = "📊 Your Transaction History\n\n"
        
        message += "💰 Recent Earnings:\n"
        if earnings:
            for earning in earnings:
                date = earning['timestamp'].strftime("%Y-%m-%d")
                message += f"• {date}: +₦{earning['amount']} ({earning['activity']})\n"
        else:
            message += "No recent earnings\n"
        
        message += "\n💸 Recent Withdrawals:\n"
        if withdrawals:
            for withdrawal in withdrawals:
                date = withdrawal['timestamp'].strftime("%Y-%m-%d")
                message += f"• {date}: -₦{withdrawal['amount']} ({withdrawal['activity']})\n"
        else:
            message += "No recent withdrawals\n"
            
        await update.message.reply_text(message)
    except Exception as e:
        await update.message.reply_text("❌ Error fetching history. Please try again later.")

def store_top_referrals(user_id, referral_count):
    """Store top referral data in the database"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO top_referrals (user_id, referral_count, timestamp) 
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (user_id) 
                    DO UPDATE SET referral_count = EXCLUDED.referral_count, timestamp = NOW()
                """, (user_id, referral_count))
                conn.commit()
    except Exception as e:
        logging.error(f"Error storing top referrals: {e}")

async def update_top_referrals():
    """Update top referrals in the database"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Create table if not exists
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS top_referrals (
                        user_id BIGINT PRIMARY KEY,
                        referral_count INT,
                        timestamp TIMESTAMP DEFAULT NOW()
                    )
                """)
                
                # Get all referrers and their counts
                for user_id, referred_users in referrals.items():
                    store_top_referrals(user_id, len(referred_users))
    except Exception as e:
        logging.error(f"Error updating top referrals: {e}")

# Update show_top_referrals to use database
async def show_top_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show top referrals from database"""
    target_message = update.message or update.callback_query.message
    
    # Show loading animation
    await show_loading_animation(target_message, "Loading top referrers", 1)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT user_id, referral_count 
                    FROM top_referrals 
                    ORDER BY referral_count DESC 
                    LIMIT 5
                """)
                top_referrers = cur.fetchall()

        message = "🏆 Top 5 Referrers:\n\n"
        
        for i, referrer in enumerate(top_referrers, 1):
            try:
                user = await context.bot.get_chat(referrer['user_id'])
                username = f"@{user.username}" if user.username else f"User {referrer['user_id']}"
                message += f"{i}. {username} - {referrer['referral_count']} referrals\n"
            except Exception as e:
                message += f"{i}. User {referrer['user_id']} - {referrer['referral_count']} referrals\n"

        if not top_referrers:
            message += "No referrals yet!"

        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
        await target_message.edit_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logging.error(f"Error showing top referrals: {e}")
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
        await target_message.edit_text(
            "❌ Error loading top referrals. Please try again later.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def get_user_id_from_input(context: ContextTypes.DEFAULT_TYPE, input_str: str) -> int:
    """Helper function to get user ID from either username or ID"""
    if not input_str:
        return None
        
    try:
        # First try parsing as user ID
        return int(input_str)
    except ValueError:
        try:
            # If not a number, try as username
            username = input_str.lstrip('@')
            
            # Try to get user from chat
            chat = await context.bot.get_chat(f"@{username}")
            return chat.id
        except Exception as e:
            print(f"Error getting user ID for input '{input_str}': {str(e)}")
            return None

# Add this command handler for the /info command
async def command_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /info command to fetch user information by ID or username"""
    try:
        # Get the target user ID or username from arguments
        if context.args:
            input_str = context.args[0]
            if input_str.startswith('@'):
                # If input is a username, fetch user ID
                try:
                    user = await context.bot.get_chat(input_str)
                    target_user_id = user.id
                except Exception as e:
                    await update.message.reply_text(f"❌ Could not find user with username {input_str}. Error: {e}")
                    return
            else:
                # If input is a user ID, parse it
                try:
                    target_user_id = int(input_str)
                except ValueError:
                    await update.message.reply_text("❌ Invalid user ID format. Please provide a valid ID or username.")
                    return
        else:
            # Default to the command issuer's ID if no argument is provided
            target_user_id = update.effective_user.id

        # Fetch user data
        balance = get_user_balance(target_user_id)
        referrals = get_referrals(target_user_id)
        referral_count = len(referrals)
        is_verified = is_user_verified(target_user_id)

        # Format user information
        info_message = (
            f"👤 User Information\n"
            f"User ID: {target_user_id}\n"
            f"Balance: ₦{balance}\n"
            f"Total Referrals: {referral_count}\n"
            f"Verified: {'✅' if is_verified else '❌'}\n"
        )

        await update.message.reply_text(info_message)
    except Exception as e:
        logging.error(f"Error in command_info: {e}")
        await update.message.reply_text("❌ An error occurred while fetching user information. Please try again later.")

def process_milestone_reward(user_id: int, ref_count: int) -> int:
    """Process milestone rewards and return bonus amount"""
    milestone_rewards = {
        10: 500,    # ₦500 for 5 referrals
        20: 1000,  # ₦1000 for 10 referrals
        30: 1500,  # ₦1500 for 20 referrals
        50: 4500,  # ₦5000 for 50 referrals
        100:5000 # ₦10000 for 100 referrals
    }
    
    reward = 0
    for milestone, amount in milestone_rewards.items():
        if ref_count == milestone:
            reward = amount
            break
            
    if reward > 0:
        update_user_balance(user_id, reward)
        log_user_activity(user_id, f"milestone_reward_{ref_count}")
        
    return reward

def get_total_earnings(user_id: int) -> dict:
    """Get breakdown of user's total earnings"""
    try:
        # Fetch referrals and calculate referral earnings
        referrals_list = get_referrals(user_id)
        referral_earnings = len(referrals_list) * REFERRAL_BONUS

        # Fetch task earnings (assuming a function exists to fetch task earnings)
        task_earnings = get_user_task_earnings(user_id)

        # Fetch current balance
        current_balance = get_user_balance(user_id)

        # Calculate total earnings
        total_earnings = referral_earnings + task_earnings

        return {
            'referral_count': len(referrals_list),
            'referral_earnings': referral_earnings,
            'task_earnings': task_earnings,
            'total_earnings': total_earnings,
            'current_balance': current_balance
        }
    except Exception as e:
        logging.error(f"Error calculating total earnings for user {user_id}: {e}")
        return {
            'referral_count': 0,
            'referral_earnings': 0,
            'task_earnings': 0,
            'total_earnings': 0,
            'current_balance': 0
        }

async def show_referral_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's referral information including usernames"""
    user_id = update.effective_user.id
    target_message = update.message or update.callback_query.message
    
    # Show loading animation
    await show_loading_animation(target_message, "Loading referral info", 1)
    
    try:
        referrals_list = get_referrals(user_id)
        ref_count = len(referrals_list)
        
        # Get total earnings from referrals
        referral_earnings = ref_count * REFERRAL_BONUS
        
        # Generate referral link
        bot = await context.bot.get_me()
        referral_link = f"https://t.me/{bot.username}?start={user_id}"
        
        message = (
            f"👥 Your Referral Dashboard\n"
            f"═══════════════════\n\n"
            f"Total Referrals: {ref_count}\n"
            f"Earnings per Referral: ₦{REFERRAL_BONUS}\n"
            f"Total Earnings: ₦{referral_earnings}\n\n"
            f"Your Referral Link:\n{referral_link}\n\n"
            f"Your Referrals:\n"
        )
        
        if referrals_list:
            for i, ref_id in enumerate(referrals_list, 1):
                try:
                    ref_user = await context.bot.get_chat(ref_id)
                    username = f"@{ref_user.username}" if ref_user.username else ref_user.first_name
                    message += f"{i}. {username}\n"
                except Exception as e:
                    message += f"{i}. User {ref_id}\n"
        else:
            message += "No referrals yet. Share your link to earn!"
            
        keyboard = [
            [InlineKeyboardButton("📢 Share Link", switch_inline_query=f"Join {bot.first_name} using my referral link!")],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]
        ]
        
        await target_message.edit_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True
        )
    except Exception as e:
        logging.error(f"Error in show_referral_menu: {e}")
        await target_message.edit_text(
            "❌ Error loading referral information. Please try again.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
        )

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help menu with available commands and instructions"""
    help_text = (
        "📖 Bot Help & Commands\n"
        "═══════════════════\n\n"
        "🎯 Available Commands:\n"
        "/start - Start/restart the bot\n"
        "/info - View your account info\n"
        "/task - Submit task screenshot\n"
        "/redeem - Redeem coupon code\n"
        "/history - View transaction history\n\n"
        "💰 Earning Methods:\n"
        "• Daily Quiz: ₦50\n"
        "• Referrals: ₦80/referral\n"
        "• Tasks: ₦250/task\n"
        "• Daily Bonus: ₦25\n"
        "• Group Chat: ₦1/message (max 50/day)\n\n"
        "💳 Withdrawal Info:\n"
        "• Minimum: ₦500\n"
        "• Requirements: 5 referrals\n"
        "• Processing Time: 24h\n\n"
        "❓ Need more help? Contact @star_ies1"
    )

    keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
    
    if update.callback_query:
        await update.callback_query.message.edit_text(
            help_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            help_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

def main():
    # Get environment variables with fallbacks
    token = os.getenv("BOT_TOKEN")
    port = int(os.getenv("PORT", "8443"))
    app_name = "sub9ja-5e9153f8bf96.herokuapp.com"  # Your Heroku app name

    if not token:
        raise ValueError("No BOT_TOKEN found in environment variables")

    print("Starting bot initialization...")

    # Initialize bot application
    application = Application.builder().token(token).build()

    # Register handlers first
    # Register quiz handlers - moved before using them
    application.add_handler(CallbackQueryHandler(handle_quiz_answer, pattern="^quiz_.*"))
    application.add_handler(CallbackQueryHandler(show_quiz_menu, pattern="^quiz$"))

    # Register error handler
    application.add_error_handler(error_handler)

    # Define withdrawal handler
    withdrawal_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(handle_withdrawal_start, pattern="^withdraw$"),
            CallbackQueryHandler(handle_bank_name, pattern="^bank_")
        ],
        states={
            ACCOUNT_NUMBER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_account_number)
            ],
            BANK_NAME: [
                CallbackQueryHandler(handle_bank_name, pattern="^bank_"),
                CallbackQueryHandler(cancel_withdrawal, pattern="^cancel_withdrawal$")
            ],
            ACCOUNT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_account_name),
                CallbackQueryHandler(cancel_withdrawal, pattern="^cancel_withdrawal$")
            ],
            AMOUNT_SELECTION: [
                CallbackQueryHandler(handle_amount_selection, pattern="^amount_"),
                CallbackQueryHandler(cancel_withdrawal, pattern="^cancel_withdrawal$")
            ]
        },
        fallbacks=[
            CallbackQueryHandler(cancel_withdrawal, pattern="^cancel_withdrawal$"),
            CallbackQueryHandler(button_handler, pattern="^back_to_menu$"),
            CommandHandler("start", start)
        ]
    )

    # Define payment handler for admin payment confirmation
    payment_handler = ConversationHandler(
        entry_points=[CommandHandler("paid", handle_paid_command)],
        states={
            PAYMENT_SCREENSHOT: [MessageHandler(filters.PHOTO, handle_payment_screenshot)]
        },
        fallbacks=[CommandHandler("start", start)]
    )

    print("Registering handlers...")

    # Register conversation handlers
    application.add_handler(withdrawal_handler)
    application.add_handler(payment_handler)

    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("info", command_info))
    application.add_handler(CommandHandler("chatid", get_chat_id))
    application.add_handler(CommandHandler("generate", handle_generate_command))
    application.add_handler(CommandHandler("redeem", handle_redeem_command))
    application.add_handler(CommandHandler("task", handle_task_command))
    application.add_handler(CommandHandler("approve_task", handle_task_approval))
    application.add_handler(CommandHandler("reject_task", handle_task_rejection))
    application.add_handler(CommandHandler("reject", handle_reject_command))
    application.add_handler(CommandHandler("add", handle_add_command))
    application.add_handler(CommandHandler("deduct", handle_deduct_command))
    application.add_handler(CommandHandler("history", show_transaction_history))
    application.add_handler(CommandHandler("db", admin_dashboard))
    application.add_handler(CommandHandler("del", handle_del_command))  # Add the /del command handler
    application.add_handler(CommandHandler("id", get_user_id))  # Add the /id command handler

    # Register message and button handlers
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Register the logging handler
    application.add_handler(MessageHandler(filters.ALL, log_all_updates))

    print("Setting up webhook...")

    try:
        # Set up webhook with correct domain and path
        webhook_url = f"https://{app_name}/{token}"

        # Start the webhook
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=token,
            webhook_url=webhook_url,
            allowed_updates=Update.ALL_TYPES
        )
        print(f"Webhook set up successfully at {webhook_url}")
    except Exception as e:
        print(f"Error setting up webhook: {e}")
        return

    # Schedule periodic tasks
    application.job_queue.run_repeating(periodic_tasks, interval=86400, first=0)  # Run daily❌ An error occurred while fetching user information❌ An error occurred while fetching user information

    # Update referral membership deduction to deduct ₦100 instead of ₦1000
    async def handle_referral_membership_changes(context: ContextTypes.DEFAULT_TYPE):
        """Deduct balance if a referral leaves the channel or group"""
        for referrer_id, referred_users in referrals.items():
            for referred_id in list(referred_users):
                is_member = await check_membership(referred_id, context)
                if not is_member:
                    # Deduct 100 NGN from referrer
                    update_user_balance(referrer_id, -100)

                    # Deduct 100 NGN from the user who left
                    update_user_balance(referred_id, -100)

                    # Remove the referral
                    referred_users.remove(referred_id)
                    print(f"Removed referral {referred_id} for referrer {referrer_id}")

if __name__ == '__main__':
    main()

async def get_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /id command to fetch user ID by username"""
    if not context.args:
        await update.message.reply_text("❌ Please provide a username. Usage: /id <username>")
        return

    username = context.args[0].lstrip('@')
    try:
        user = await context.bot.get_chat(f"@{username}")
        await update.message.reply_text(f"✅ User ID for @{username}: {user.id}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error fetching user ID for @{username}: {str(e)}")
