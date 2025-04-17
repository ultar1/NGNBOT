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
        if query.message:
            await query.message.edit_text(
                "⏳ Verifying your membership...\n"
                "Please wait a moment."
            )
        else:
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

        # Fetch referral usernames
        referral_usernames = []
        for ref_id in referrals:
            try:
                ref_user = await context.bot.get_chat(ref_id)
                username = f"@{ref_user.username}" if ref_user.username else ref_user.first_name
                referral_usernames.append(username)
            except Exception as e:
                referral_usernames.append(f"User {ref_id}")

        # Format user information
        info_message = (
            f"👤 User Information\n"
            f"User ID: {target_user_id}\n"
            f"Balance: ₦{balance}\n"
            f"Total Referrals: {referral_count}\n"
            f"Verified: {'✅' if is_verified else '❌'}\n"
            f"Referrals: {', '.join(referral_usernames) if referral_usernames else 'No referrals yet'}"
        )

        await update.message.reply_text(info_message)
    except Exception as e:
        logging.error(f"Error in command_info: {e}")
        await update.message.reply_text("❌ An error occurred while fetching user information. Please try again later.")

async def command_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /id command to fetch user ID by username"""
    try:
        if not context.args or not context.args[0].startswith('@'):
            await update.message.reply_text("❌ Usage: /id <tg_username>")
            return

        username = context.args[0]
        try:
            user = await context.bot.get_chat(username)
            await update.message.reply_text(f"✅ User ID for {username}: {user.id}")
        except Exception as e:
            await update.message.reply_text(f"❌ Could not find user with username {username}. Error: {e}")
    except Exception as e:
        logging.error(f"Error in command_get_id: {e}")
        await update.message.reply_text("❌ An error occurred while fetching user ID. Please try again later.")
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
        await show_referral_menu(update,
