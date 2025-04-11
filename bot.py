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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime%s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()

# Admin Information
ADMIN_USERNAME = "star_ies1"
ADMIN_ID = 7302005705
ANNOUNCEMENT_CHANNEL = "@latestinfoult"  # Channel for announcements

# Store user data in memory
referrals = {}
user_balances = {}
pending_referrals = {}  # Store pending referrals until verification
last_signin = {}  # Track last sign in date for each user
last_withdrawal = {}  # Track last withdrawal date for each user
user_withdrawal_state = {}  # Store withdrawal process state
user_bank_info = {}  # Store user bank details
account_number_to_user = {}  # Map account numbers to user IDs
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

# Store user data in memory
last_chat_reward = {}  # Track daily chat rewards
daily_chat_count = {}  # Track number of chats per day

# Common Nigerian Banks
BANKS = [
    'Access Bank', 'First Bank', 'GT Bank', 'UBA', 'Zenith Bank',
    'Fidelity Bank', 'Union Bank', 'Sterling Bank', 'Wema Bank',
    'Stanbic IBTC', 'Polaris Bank', 'Opay', 'Palmpay', 'Kuda'
]

# Track verified status
user_verified_status = {}

# Store coupon codes
active_coupons = {}  # Format: {code: {'amount': amount, 'expires_at': datetime}}
used_coupons = {}    # Format: {code: [user_ids]}

# Store last weekly reward time
last_weekly_reward = datetime.now()

# Define conversation states
(
    ACCOUNT_NUMBER,
    BANK_NAME,
    ACCOUNT_NAME,
    AMOUNT_SELECTION,
    PAYMENT_SCREENSHOT,  # Added payment screenshot state
    LANGUAGE_SELECTION  # Added language selection state
) = range(6)  # Updated range to include new state

def generate_coupon_code(length=8):
    """Generate a random coupon code"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

async def check_and_credit_daily_bonus(user_id: int) -> bool:
    today = datetime.now().date()
    last_date = last_signin.get(user_id)
    
    if last_date is None or last_date < today:
        last_signin[user_id] = today
        user_balances[user_id] = user_balances.get(user_id, 0) + DAILY_BONUS
        return True
    return False

async def notify_admin_new_user(user_id: int, user_info: dict, referrer_id: int, context: ContextTypes.DEFAULT_TYPE):
    try:
        referrer = await context.bot.get_chat(referrer_id) if referrer_id else None
        user = await context.bot.get_chat(user_id)
        
        admin_message = (
            f"🆕 New User Verified!\n\n"
            f"User Information:\n"
            f"• ID: {user_id}\n"
            f"• Username: @{user.username if user.username else 'None'}\n"
            f"• Name: {user.first_name} {user.last_name if user.last_name else ''}\n\n"
        )
        
        if referrer:
            admin_message += (
                f"Referred by:\n"
                f"• ID: {referrer_id}\n"
                f"• Username: @{referrer.username if referrer.username else 'None'}\n"
                f"• Name: {referrer.first_name} {referrer.last_name if referrer.last_name else ''}"
            )
        else:
            admin_message += "No referrer (direct join)"
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_message
        )
    except Exception as e:
        logging.error(f"Failed to send admin notification: {e}")

# Add logging to debug referral and notification logic
async def process_pending_referral(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Processing pending referral for user_id: {user_id}")
    referrer_id = pending_referrals.get(user_id)
    if referrer_id:
        logging.info(f"Found referrer_id: {referrer_id} for user_id: {user_id}")

        # Check if this is not a self-referral and user hasn't been referred before
        if referrer_id != user_id and user_id not in referrals.get(referrer_id, set()):
            # Add to referrals and credit bonus
            referrals.setdefault(referrer_id, set()).add(user_id)
            user_balances[referrer_id] = user_balances.get(referrer_id, 0) + REFERRAL_BONUS
            logging.info(f"Referral bonus credited to referrer_id: {referrer_id}.")

            try:
                # Notify referrer
                await context.bot.send_message(
                    chat_id=referrer_id,
                    text=f"🎉 Your referral has been verified!\nYou earned ₦{REFERRAL_BONUS}!\nNew balance: ₦{user_balances[referrer_id]}"
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
        # If update is a Message object directly
        await update.edit_text(
            message_text,
            reply_markup=reply_markup
        )

# Fix the issue where update.message is None in button-related functions
async def show_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE, show_back=False):
    """Show dashboard with optional back button, including quiz option"""
    user = update.effective_user
    balance = user_balances.get(user.id, 0)
    ref_count = len(referrals.get(user.id, set()))
    daily_chats = daily_chat_count.get(user.id, 0)
    chats_remaining = MAX_DAILY_CHAT_REWARD - daily_chats
    
    keyboard = [
        [
            InlineKeyboardButton("👥 Referrals", callback_data='my_referrals'),
            InlineKeyboardButton("💰 Balance", callback_data='balance')
        ],
        [
            InlineKeyboardButton("💸 Withdraw", callback_data='withdraw')
        ],
        [
            InlineKeyboardButton("📅 Daily Bonus", callback_data='daily_bonus'),
            InlineKeyboardButton("📝 Tasks", callback_data='tasks')
        ],
        [
            InlineKeyboardButton("🧠 Quiz", callback_data='quiz'),  # Add quiz button
            InlineKeyboardButton("🏆 Top Referrals", callback_data='top_referrals')  # Add top referrals button
        ]
    ]
    
    # Add back button if requested
    if show_back:
        keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    dashboard_text = (
        f"🎯 Quick Stats:\n"
        f"• Balance: {balance} points (₦{balance})\n"
        f"• Total Referrals: {ref_count}\n"
        f"• Earnings per referral: {REFERRAL_BONUS} points (₦{REFERRAL_BONUS})\n"
        f"• Daily bonus: {DAILY_BONUS} points (₦{DAILY_BONUS})\n"
        f"• Chat earnings: ₦1 per chat\n"
        f"• Today's chats: {daily_chats}/50 (₦{daily_chats})\n"
        f"• Remaining chat earnings: {chats_remaining} (₦{chats_remaining})\n"
        f"• Min. withdrawal: {MIN_WITHDRAWAL} points (₦{MIN_WITHDRAWAL})\n\n"
        "Choose an option below:"
    )
    
    # Use callback_query.message if update.message is None
    target_message = update.message or update.callback_query.message

    if update.callback_query:
        await target_message.edit_text(
            dashboard_text,
            reply_markup=reply_markup
        )
    else:
        await target_message.reply_text(
            dashboard_text,
            reply_markup=reply_markup
        )

# Update the referral menu to include the user's referral link
async def show_referral_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ref_count = len(referrals.get(user.id, set()))
    referral_link = f"https://t.me/{BOT_USERNAME}?start={user.id}"

    keyboard = [
        [InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    target_message = update.message or update.callback_query.message

    await target_message.edit_text(
        f"You have {ref_count} referrals! 👥\n"
        f"Total earnings: {ref_count * REFERRAL_BONUS} points (₦{ref_count * REFERRAL_BONUS})\n\n"
        f"Your Telegram Name: {user.first_name} {user.last_name if your.last_name else ''}\n\n"
        f"🔗 Your Referral Link:\n{referral_link}\n\n"
        f"Share this link with your friends to earn ₦{REFERRAL_BONUS} for each referral!",
        reply_markup=reply_markup
    )

# Define the file path for storing user activities
USER_ACTIVITY_FILE = "user_activities.json"

def load_user_activities():
    """Load user activities from the JSON file."""
    try:
        with open(USER_ACTIVITY_FILE, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_user_activities():
    """Save user activities to the JSON file."""
    with open(USER_ACTIVITY_FILE, "w") as file:
        json.dump(user_activities, file)

# Ensure the directory for the user activities file exists
if not os.path.exists(USER_ACTIVITY_FILE):
    with open(USER_ACTIVITY_FILE, "w") as file:
        json.dump({}, file)

# Load user activities at startup
user_activities = load_user_activities()

# Update user activity logging in relevant functions
def log_user_activity(user_id, activity):
    """Log a user's activity."""
    if user_id not in user_activities:
        user_activities[user_id] = []
    user_activities[user_id].append({
        "activity": activity,
        "timestamp": datetime.now().isoformat()
    })
    save_user_activities()

# Update the start command to include language selection
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command with verification check"""
    user = update.effective_user

    # Log the /start command activity
    log_user_activity(user.id, "Started the bot")

    # Extract referrer ID from the start parameter
    args = context.args
    if args:
        try:
            referrer_id = int(args[0])
            if referrer_id != user.id:  # Prevent self-referral
                pending_referrals[user.id] = referrer_id
                logging.info(f"Added pending referral: {user.id} referred by {referrer_id}")
        except ValueError:
            logging.warning(f"Invalid referrer ID in /start command: {args[0]}")

    # Check if user is verified
    is_verified = user_verified_status.get(user.id, False)

    if not is_verified:
        await show_verification_menu(update, context)
        return

    # For verified users, show dashboard
    await show_dashboard(update, context)

async def handle_verify_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle verification button click"""
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer("Checking membership status...")
    
    # Check membership
    is_member = await check_membership(user_id, context)
    if not is_member:
        await show_join_message(update, context)
        return
    
    # Mark user as verified
    user_verified_status[user_id] = True
    
    # Give welcome bonus ONLY IF this is their first verification and they're not in user_balances
    if user_id not in user_balances:
        print(f"Adding welcome bonus of {WELCOME_BONUS} to new user {user_id}")
        user_balances[user_id] = WELCOME_BONUS
        referrals[user_id] = set()
        await query.message.reply_text(
            f"🎉 Welcome! You've received {WELCOME_BONUS} points (₦{WELCOME_BONUS}) as a welcome bonus!"
        )
    
    # Process any pending referrals
    await process_pending_referral(user_id, context)
    
    # Show dashboard
    await show_dashboard(update, context)
    return

async def can_withdraw_today(user_id: int) -> bool:
    today = datetime.now().date()
    last_date = last_withdrawal.get(user_id)
    return last_date is None or last_date < today

async def verify_referrals_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Verify that all referrals are still members"""
    if user_id not in referrals:
        return True
        
    all_members = True
    not_in_channel = []
    
    for referred_id in referrals[user_id]:
        is_member = await check_membership(referred_id, context)
        if not is_member:
            all_members = False
            not_in_channel.append(referred_id)
    
    return all_members, not_in_channel

async def handle_withdrawal_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the withdrawal process"""
    query = update.callback_query
    user_id = query.from_user.id
    
    print(f"Starting withdrawal process for user {user_id}")  # Add debug logging
    
    # First check user's membership
    is_member = await check_membership(user_id, context)
    if not is_member:
        print(f"User {user_id} is not a member")  # Add debug logging
        await query.message.edit_text(
            "❌ You must be a member of our channel and group to withdraw!\n"
            "Please join and try again.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
        )
        return ConversationHandler.END
    
    # Check balance first
    balance = user_balances.get(user_id, 0)
    if balance < MIN_WITHDRAWAL:
        print(f"User {user_id} has insufficient balance: {balance}")  # Add debug logging
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
        print(f"User {user_id} has saved bank details")  # Add debug logging
        await query.message.edit_text(
            f"Found saved bank details:\nBank: {saved_info['bank']}\nAccount: {saved_info['account_number']}\n\nWould you like to use this account?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ACCOUNT_NUMBER
    
    # No saved details, proceed with normal flow
    print(f"User {user_id} needs to enter bank details")  # Add debug logging
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

async def handle_account_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle account name input"""
    user_id = update.effective_user.id
    account_name = update.message.text.strip()
    
    if len(account_name) < 3:
        await update.message.reply_text(
            "❌ Invalid account name! Name must be at least 3 characters long.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data='cancel_withdrawal')]])
        )
        return ACCOUNT_NAME
    
    # Save account name
    context.user_data['withdrawal']['account_name'] = account_name
    
    # Show amount selection
    balance = user_balances.get(user_id, 0)
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
    
    # Save bank info for future use
    user_bank_info[user_id] = {
        'account_number': withdrawal_data['account_number'],
        'bank': withdrawal_data['bank'],
        'account_name': withdrawal_data['account_name']
    }
    
    # Verify amount
    balance = user_balances.get(user_id, 0)
    if amount > balance:
        await query.message.edit_text(
            "❌ Insufficient balance for this withdrawal amount!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
        )
        return ConversationHandler.END
    
    # Process withdrawal and store withdrawal state
    user_balances[user_id] = balance - amount
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
        f"Remaining balance: ₦{user_balances[user_id]}\n\n"
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
            user_balances[target_user_id] = user_balances.get(target_user_id, 0) + refund_amount
            
            # Notify user about rejection and refund
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(f"❌ Your withdrawal of ₦{refund_amount} has been rejected.\n"
                      f"Reason: {reason}\n\n"
                      f"✅ Your {refund_amount} points have been refunded to your balance.\n"
                      f"New balance: ₦{user_balances[target_user_id]}")
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
        
        user_balances[target_user_id] = user_balances.get(target_user_id, 0) + amount
        
        # Notify user
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"✨ {amount} points (₦{amount}) have been added to your balance by admin!"
        )
        
        await update.message.reply_text(
            f"✅ Added {amount} points to user {target_user_id}\n"
            f"New balance: {user_balances[target_user_id]} points"
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
        
        current_balance = user_balances.get(target_user_id, 0)
        if current_balance < amount:
            await update.message.reply_text(
                f"❌ User only has {current_balance} points, cannot deduct {amount} points!"
            )
            return
        
        user_balances[target_user_id] = current_balance - amount
        
        # Notify user
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"📛 {amount} points (₦{amount}) have been deducted from your balance by admin."
        )
        
        await update.message.reply_text(
            f"✅ Deducted {amount} points from user {target_user_id}\n"
            f"New balance: {user_balances[target_user_id]} points"
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
            f"Code: `{escaped_code}`\n"
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
    user_balances[user.id] = user_balances.get(user.id, 0) + amount
    used_coupons[code].append(user.id)
    
    # Calculate remaining time
    time_remaining = coupon_data['expires_at'] - current_time
    minutes_remaining = int(time_remaining.total_seconds() / 60)
    
    await update.message.reply_text(
        f"🎉 Coupon code redeemed successfully!\n"
        f"Added ₦{amount} to your balance.\n"
        f"New balance: ₦{user_balances[user.id]}\n\n"
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

# Update the top referral menu to edit the existing menu instead of dropping another menu
async def show_top_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top_referrers = sorted(referrals.items(), key=lambda x: len(x[1]), reverse=True)[:5]
    message = "🏆 Top 5 Referrers:\n\n"

    for i, (user_id, referred_users) in enumerate(top_referrers, start=1):
        message += f"{i}. User ID: {user_id} - Referrals: {len(referred_users)}\n"

    if not top_referrers:
        message += "No referrals yet!"

    keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]

    target_message = update.message or update.callback_query.message

    await target_message.edit_text(message, reply_markup=InlineKeyboardMarkup(keyboard))

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
            user_balances[user_id] = user_balances.get(user_id, 0) + reward
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
                for i, (user_id, ref_count) in enumerate(top_referrers, 1):
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
    user = update.effective_user

    if not await is_admin(user.id):
        await update.message.reply_text("❌ This command is only for admins!")
        return

    if not context.args or len(context.args) < 1:
        return

    try:
        target_user_id = int(context.args[0])
        balance = user_balances.get(target_user_id, 0)
        ref_count = len(referrals.get(target_user_id, set()))
        total_earnings = ref_count * REFERRAL_BONUS
        last_signin_date = last_signin.get(target_user_id, None)

        next_bonus = "Available Now! 🎁"
        if last_signin_date and last_signin_date == datetime.now().date():
            tomorrow = datetime.now() + timedelta(days=1)
            tomorrow = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
            time_until = tomorrow - datetime.now()
            hours = int(time_until.total_seconds() // 3600)
            minutes = int((time_until.total_seconds() % 3600) // 60)
            next_bonus = f"in {hours}h {minutes}m ⏳"

        info_message = (
            f"👤 User Information\n"
            f"───────────────\n"
            f"ID: {target_user_id}\n"
            f"Balance: {balance} points (₦{balance})\n"
            f"Total Referrals: {ref_count}\n"
            f"Referral Earnings: {total_earnings} points (₦{total_earnings})\n"
            f"Next Daily Bonus: {next_bonus}\n"
            f"Min. Withdrawal: {MIN_WITHDRAWAL} points (₦{MIN_WITHDRAWAL})"
        )

        await update.message.reply_text(info_message)
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

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
            user_balances[member_id] = user_balances.get(member_id, 0) + CHAT_REWARD
        await update.message.reply_text(
            f"💬 Thanks for being active in the group! Each member earned ₦{CHAT_REWARD}.\n"
            f"Today's group chat earnings: {daily_chat_count[chat.id]}/50."
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    # Handle verification button
    if query.data == 'verify_membership':
        await handle_verify_membership(update, context)
        return

    if query.data == 'check_membership':
        is_member = await check_membership(user_id, context)
        if (is_member):
            await query.answer("✅ Membership verified!")
            await show_dashboard(update, context)
        else:
            await query.answer("❌ Please join both the channel and group!")
            await show_join_message(query.message, context)
        return

    if query.data == 'back_to_menu':
        await query.answer("🔙 Returning to main menu...")
        await show_dashboard(update, context)
        return

    elif query.data == 'my_referrals':
        await query.answer()
        await show_referral_menu(update, context)
        return

    elif query.data == 'top_referrals':
        await query.answer()
        await show_top_referrals(update, context)
        return

    elif query.data == 'daily_bonus':
        daily_bonus_earned = await check_and_credit_daily_bonus(user_id)
        if daily_bonus_earned:
            await query.answer("✅ Daily bonus credited!")
            await query.message.edit_text(
                f"🎉 You have received your daily bonus of {DAILY_BONUS} points (₦{DAILY_BONUS})!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
            )
        else:
            await query.answer("❌ You have already claimed your daily bonus today!")
        return

    elif query.data == 'balance':
        balance = user_balances.get(user_id, 0)
        await query.answer()
        await query.message.edit_text(
            f"Your current balance: {balance} points (₦{balance}) 💰",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
        )
        return

    elif query.data == 'tasks':
        await handle_tasks_button(update, context)
        return

    elif query.data == 'use_saved_account':
        saved_info = user_bank_info.get(user_id)
        if saved_info:
            context.user_data['withdrawal'] = saved_info.copy()
            await handle_amount_selection(update, context)
        return

    elif query.data == 'new_account':
        await query.message.edit_text(
            "Please enter your account number (10 digits):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data='cancel_withdrawal')]])
        )
        return ACCOUNT_NUMBER

    # Handle quiz button
    if query.data == 'quiz':
        await show_quiz_menu(update, context)
        return

    if query.data.startswith('quiz_'):
        await handle_quiz_answer(update, context)
        return

    await query.answer("❌ Unknown action.")

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
        user_balances[target_user_id] = user_balances.get(target_user_id, 0) + TASK_REWARD
        
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
    """Handle tasks button click"""
    keyboard = [
        [InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]
    ]
    
    await update.callback_query.message.edit_text(
        "📝 Task Instructions:\n\n"
        "1. Join our channel and group\n"
        "2. Share your referral link on any social media\n"
        "3. Take a screenshot showing:\n"
        "   • Your post with the referral link, OR\n"
        "   • Your content/review about our bot\n"
        "4. Send the screenshot using /task command\n\n"
        f"Reward: ₦{TASK_REWARD} per approved task\n\n"
        "Note: Your task will be reviewed and approved by admin",
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
                f"• Total Referrals: {len(referrals.get(referrer_id, set()))}"
            )
        else:
            admin_message += "Direct Join (No Referrer)"
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_message
        )
    except Exception as e:
        print(f"Failed to send admin notification: {e}")

import random

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
async def show_quiz_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the quiz menu with a random question and a 10-second timer"""
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

    # Save the correct answer in context
    context.user_data['quiz_answer'] = correct_answer
    context.user_data['quiz_active'] = True

    # Create buttons for options
    keyboard = [[InlineKeyboardButton(option, callback_data=f'quiz_{option}')] for option in options]
    keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')])

    await update.callback_query.message.edit_text(
        f"🧠 Quiz Time!\n\n{question}\n\nYou have 10 seconds to answer!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    # Start a 10-second timer
    await asyncio.sleep(10)

    # Check if the quiz is still active
    if context.user_data.get('quiz_active', False):
        context.user_data['quiz_active'] = False
        user_quiz_status[user_id] = today  # Mark as failed for today
        await update.callback_query.message.edit_text(
            "⏰ Time's up! You didn't answer in time. Try again tomorrow!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
        )

async def handle_quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the user's quiz answer"""
    query = update.callback_query
    user_id = query.from_user.id
    selected_option = query.data.replace('quiz_', '')

    # Check the correct answer
    correct_answer = context.user_data.get('quiz_answer')
    if not correct_answer:
        await query.answer("❌ Something went wrong. Please try again later.")
        return

    if selected_option == correct_answer:
        # Mark quiz as completed for today
        user_quiz_status[user_id] = datetime.now().date()

        # Reward the user
        user_balances[user_id] = user_balances.get(user_id, 0) + 50
        await query.message.edit_text(
            f"✅ Correct! You have earned ₦50.\nYour new balance is ₦{user_balances[user_id]}.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
        )
    else:
        # Mark quiz as failed for today
        user_quiz_status[user_id] = datetime.now().date()
        await query.message.edit_text(
            f"❌ Wrong answer! The correct answer was: {correct_answer}. Try again tomorrow!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
        )

# Update referral milestones to start from 50
MILESTONES = [50, 100, 200]  # Define referral milestones

async def check_milestones(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Check if the user has reached a referral milestone"""
    ref_count = len(referrals.get(user_id, set()))
    for milestone in MILESTONES:
        if ref_count == milestone:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎉 Congratulations! You've reached {milestone} referrals and earned a special reward!"
            )
            # Add a reward for reaching the milestone
            user_balances[user_id] = user_balances.get(user_id, 0) + 1000  # Example reward
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
    """Show the user's transaction history"""
    user_id = update.effective_user.id
    history = transaction_history.get(user_id, [])

    if not history:
        await update.message.reply_text("📜 You have no transaction history.")
        return

    message = "📜 Transaction History:\n\n"
    for entry in history:
        message += f"• {entry['date']}: {entry['type'].capitalize()} ₦{entry['amount']}\n"

    await update.message.reply_text(message)

# Add admin dashboard
async def admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the admin dashboard"""
    user = update.effective_user

    if not await is_admin(user.id):
        await update.message.reply_text("❌ This command is only for admins!")
        return

    total_users = len(user_balances)
    total_referrals = sum(len(refs) for refs in referrals.values())
    total_balance = sum(user_balances.values())
    total_withdrawals = sum(state['amount'] for state in user_withdrawal_state.values())
    pending_withdrawals = len(user_withdrawal_state)

    message = (
        f"📊 Admin Dashboard:\n\n"
        f"• Total Users: {total_users}\n"
        f"• Total Referrals: {total_referrals}\n"
        f"• Total Balance Across Users: ₦{total_balance}\n"
        f"• Total Withdrawals Processed: ₦{total_withdrawals}\n"
        f"• Pending Withdrawals: {pending_withdrawals}\n"
        f"• Weekly Top Referrer Reward: ₦1000 (1st), ₦500 (2nd)\n"
        f"• Referral Milestones: {', '.join(map(str, MILESTONES))} referrals\n"
    )

    await update.message.reply_text(message)

# Fix /info command
async def handle_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to get user bot info"""
    user = update.effective_user

    if not await is_admin(user.id):
        await update.message.reply_text("❌ This command is only for admins!")
        return

    if not context.args or len(context.args) < 1:
        await update.message.reply_text("❌ Usage: /info <user_id>")
        return

    try:
        target_user_id = int(context.args[0])
        balance = user_balances.get(target_user_id, 0)
        ref_count = len(referrals.get(target_user_id, set()))
        total_earnings = ref_count * REFERRAL_BONUS

        info_message = (
            f"👤 User Information\n"
            f"───────────────\n"
            f"ID: {target_user_id}\n"
            f"Balance: {balance} points (₦{balance})\n"
            f"Total Referrals: {ref_count}\n"
            f"Referral Earnings: {total_earnings} points (₦{total_earnings})\n"
        )

        await update.message.reply_text(info_message)
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

# Define user_quiz_status to track quiz participation
user_quiz_status = {}  # Format: {user_id: date}

# Define show_verification_menu function
async def show_verification_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the verification menu to the user"""
    keyboard = [
        [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME}"),
         InlineKeyboardButton("👥 Join Group", url=REQUIRED_GROUP)],
        [InlineKeyboardButton("✅ Verify Membership", callback_data='verify_membership')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "✅ To complete your verification, please:\n"
        "1. Join our channel\n"
        "2. Join our group\n"
        "3. Click 'Verify Membership' button",
        reply_markup=reply_markup
    )

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
                user_balances[referrer_id] = max(0, user_balances.get(referrer_id, 0) - LEAVE_PENALTY)

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

# Define the file path for storing user balances
USER_BALANCES_FILE = "user_balances.json"

def load_user_balances():
    """Load user balances from the JSON file."""
    try:
        with open(USER_BALANCES_FILE, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_user_balances():
    """Save user balances to the JSON file."""
    with open(USER_BALANCES_FILE, "w") as file:
        json.dump(user_balances, file)

# Load user balances at startup
user_balances = load_user_balances()

# Update user balance whenever it changes
def update_user_balance(user_id, amount):
    """Update the balance of a user and save it to the file."""
    user_balances[user_id] = user_balances.get(user_id, 0) + amount
    save_user_balances()

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
    application.add_handler(CommandHandler("info", get_user_info))
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
    application.job_queue.run_repeating(periodic_tasks, interval=86400, first=0)  # Run daily

    # Update referral membership deduction to deduct ₦100 instead of ₦1000
    async def handle_referral_membership_changes(context: ContextTypes.DEFAULT_TYPE):
        """Deduct balance if a referral leaves the channel or group"""
        for referrer_id, referred_users in referrals.items():
            for referred_id in list(referred_users):
                is_member = await check_membership(referred_id, context)
                if not is_member:
                    # Deduct 100 NGN from referrer
                    user_balances[referrer_id] = max(0, user_balances.get(referrer_id, 0) - 100)

                    # Deduct 100 NGN from the user who left
                    user_balances[referred_id] = max(0, user_balances.get(referred_id, 0) - 100)

                    # Remove the referral
                    referred_users.remove(referred_id)

if __name__ == '__main__':
    main()