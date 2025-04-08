import os
import random
import string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMemberUpdated
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters, ConversationHandler, ChatMemberHandler
from telegram.constants import ChatMemberStatus
from dotenv import load_dotenv
from datetime import datetime, timedelta

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
WELCOME_BONUS = 100  # ₦100
REFERRAL_BONUS = 80  # Changed from 70 to 80
DAILY_BONUS = 25  # ₦25
TOP_REFERRER_BONUS = 1000  # ₦1000 weekly bonus for top 5 referrers
MIN_WITHDRAWAL = 500  # ₦500 minimum withdrawal
MAX_WITHDRAWAL = 1000  # ₦1000 maximum withdrawal
LEAVE_PENALTY = 200  # ₦200 penalty for leaving channel/group
CHAT_REWARD = 1  # ₦1 per chat message
MAX_DAILY_CHAT_REWARD = 50  # Maximum ₦50 from chat per day
TASK_REWARD = 100  # ₦100 reward for completing task
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
    PAYMENT_SCREENSHOT  # Added payment screenshot state
) = range(5)  # Updated range to include new state

# Store CAPTCHA data
user_captcha = {}  # Format: {user_id: {'code': '1234', 'attempts': 0}}
MAX_CAPTCHA_ATTEMPTS = 3

def generate_captcha():
    """Generate a 4-digit CAPTCHA code"""
    return ''.join(random.choices(string.digits, k=4))

async def send_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Send CAPTCHA verification to user"""
    captcha_code = generate_captcha()
    user_captcha[user_id] = {'code': captcha_code, 'attempts': 0}
    
    keyboard = [[InlineKeyboardButton("🔄 Generate New CAPTCHA", callback_data='new_captcha')]]
    
    await update.message.reply_text(
        f"🔒 Security Check\n\n"
        f"Please enter this code: {captcha_code}\n\n"
        f"Type the code and send it as a message.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return True

async def verify_captcha(message: str, user_id: int) -> bool:
    """Verify CAPTCHA input"""
    if user_id not in user_captcha:
        return False
        
    captcha_data = user_captcha[user_id]
    captcha_data['attempts'] += 1
    
    if captcha_data['code'] == message.strip():
        del user_captcha[user_id]
        return True
        
    if captcha_data['attempts'] >= MAX_CAPTCHA_ATTEMPTS:
        del user_captcha[user_id]
        
    return False

async def handle_new_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new CAPTCHA generation button"""
    query = update.callback_query
    user_id = query.from_user.id
    
    # Generate new CAPTCHA
    captcha_code = generate_captcha()
    user_captcha[user_id] = {'code': captcha_code, 'attempts': 0}
    
    keyboard = [[InlineKeyboardButton("🔄 Generate New CAPTCHA", callback_data='new_captcha')]]
    
    await query.message.edit_text(
        f"🔒 Security Check\n\n"
        f"Please enter this code: {captcha_code}\n\n"
        f"Type the code and send it as a message.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await query.answer("New CAPTCHA generated!")

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
        print(f"Failed to send admin notification: {e}")

async def process_pending_referral(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    if user_id in pending_referrals:
        referrer_id = pending_referrals[user_id]
        if referrer_id != user_id and referrer_id in referrals:
            referrals[referrer_id].add(user_id)
            user_balances[referrer_id] = user_balances.get(referrer_id, 0) + REFERRAL_BONUS
            
            # Notify admin about the new verified user
            await notify_admin_new_user(user_id, None, referrer_id, context)
            
            try:
                await context.bot.send_message(
                    chat_id=referrer_id,
                    text=f"🎉 Your referral has been verified! You earned {REFERRAL_BONUS} points (₦{REFERRAL_BONUS})!"
                )
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ You've been verified! Your referrer earned {REFERRAL_BONUS} points (₦{REFERRAL_BONUS})!"
                )
            except:
                pass
        else:
            # If no referrer, still notify admin about new user
            await notify_admin_new_user(user_id, None, None, context)
            
        del pending_referrals[user_id]

async def check_and_handle_membership_change(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        # For debugging
        print(f"Checking membership for user {user_id}")
        
        # Check channel membership
        try:
            channel_member = await context.bot.getChatMember(chat_id=REQUIRED_CHANNEL, user_id=user_id)
            print(f"Channel status for user {user_id}: {channel_member.status}")
        except Exception as e:
            print(f"Error checking channel membership: {str(e)}")
            return False
            
        # Check group membership using numeric ID
        try:
            group_member = await context.bot.getChatMember(chat_id=GROUP_USERNAME, user_id=user_id)
            print(f"Group status for user {user_id}: {group_member.status}")
        except Exception as e:
            print(f"Error checking group membership: {str(e)}")
            return False
        
        # Use correct ChatMemberStatus values
        valid_member_status = [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER  # Changed from CREATOR to OWNER
        ]
        
        is_verified = (
            channel_member.status in valid_member_status and
            group_member.status in valid_member_status
        )
        
        print(f"Is user {user_id} verified? {is_verified}")
        
        # Check if user was previously verified and now isn't
        was_verified = user_verified_status.get(user_id, False)
        if was_verified and not is_verified:
            # Apply penalty
            current_balance = user_balances.get(user_id, 0)
            user_balances[user_id] = max(0, current_balance - LEAVE_PENALTY)  # Don't go below 0
            
            try:
                # Notify user about the penalty
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"⚠️ You left the channel or group!\n"
                         f"A penalty of {LEAVE_PENALTY} points (₦{LEAVE_PENALTY}) has been deducted.\n"
                         f"Please rejoin to continue using the bot."
                )
                
                # Notify admin
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"👤 User Left Alert!\n"
                         f"User ID: {user_id}\n"
                         f"Penalty Applied: {LEAVE_PENALTY} points (₦{LEAVE_PENALTY})\n"
                         f"New Balance: {user_balances[user_id]} points"
                )
            except Exception as e:
                print(f"Failed to send penalty notification: {e}")
        
        # Update verified status
        user_verified_status[user_id] = is_verified
        
        if is_verified:
            await process_pending_referral(user_id, context)
        
        return is_verified
    except Exception as e:
        print(f"Error in check_and_handle_membership_change: {str(e)}")
        return False

check_membership = check_and_handle_membership_change

# Provide channel and group buttons during verification if the user isn't in them
async def show_join_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME}")],
        [InlineKeyboardButton("👥 Join Group", url=REQUIRED_GROUP)],
        [InlineKeyboardButton("✅ Check Membership", callback_data='check_membership')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚠️ You must join our channel and group to use this bot!\n\n"
        "1. Join our channel\n"
        "2. Join our group\n"
        "3. Click 'Check Membership' button",
        reply_markup=reply_markup
    )

# Fix the issue where update.message is None in button-related functions
async def show_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE, show_back=False):
    """Show dashboard with optional back button"""
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
        f"Your Telegram Name: {user.first_name} {user.last_name if user.last_name else ''}\n\n"
        f"🔗 Your Referral Link:\n{referral_link}\n\n"
        f"Share this link with your friends to earn ₦{REFERRAL_BONUS} for each referral!",
        reply_markup=reply_markup
    )

# Update the start command to show channel and group buttons if the user isn't in them
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Check if user needs CAPTCHA verification
    if not user.id in user_balances and not user.id in user_captcha:
        await send_captcha(update, context, user.id)
        return
    
    # If user has pending CAPTCHA, verify it
    if user.id in user_captcha:
        if update.message.text.startswith('/start'):
            await update.message.reply_text(
                "❌ Please complete the CAPTCHA verification first!\n"
                "Enter the code shown above."
            )
            return
            
        is_verified = await verify_captcha(update.message.text, user.id)
        if not is_verified:
            remaining_attempts = MAX_CAPTCHA_ATTEMPTS - user_captcha.get(user.id, {}).get('attempts', 0)
            if remaining_attempts > 0:
                await update.message.reply_text(
                    f"❌ Wrong code! You have {remaining_attempts} attempts remaining."
                )
            else:
                await update.message.reply_text(
                    "❌ Too many failed attempts. Please start over with /start"
                )
            return
        
        await update.message.reply_text("✅ CAPTCHA verified successfully!")

    # Initialize verified status if new user
    if user.id not in user_verified_status:
        user_verified_status[user.id] = False

    is_existing_user = user.id in user_balances

    # Check membership
    is_member = await check_membership(user.id, context)
    if not is_member:
        await show_join_message(update, context)
        return

    # Show verification menu first
    keyboard = [
        [InlineKeyboardButton("✅ Verify Membership", callback_data='verify_membership')],
    ]

    # Store referral info if this is a referred user
    if context.args and len(context.args) > 0:
        try:
            referrer_id = int(context.args[0])
            if referrer_id != user.id:
                pending_referrals[user.id] = referrer_id
        except ValueError:
            pass

    welcome_text = (
        f"👋 Welcome{' back' if is_existing_user else ''} to Sub9ja Bot!\n\n"
        "📱 Earn money by:\n"
        "• Referring friends\n"
        "• Completing tasks\n"
        "• Daily bonuses\n"
        "• Chat rewards\n\n"
        "✅ Please verify your membership to continue:"
    )

    await update.message.reply_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_verify_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle verification button click"""
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer()
    
    # Check membership
    is_member = await check_membership(user_id, context)
    if not is_member:
        await show_join_message(update, context)
        return
    
    is_existing_user = user_id in user_balances
    
    # Handle new users
    if not is_existing_user:
        user_balances[user_id] = WELCOME_BONUS
        referrals[user_id] = set()
        await query.message.edit_text(
            f"🎉 Welcome! You've received {WELCOME_BONUS} points (₦{WELCOME_BONUS}) as a welcome bonus!"
        )
    
    # Check for daily sign-in bonus
    daily_bonus_earned = await check_and_credit_daily_bonus(user_id)
    if daily_bonus_earned:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"📅 Daily Sign-in Bonus!\nYou've earned {DAILY_BONUS} points (₦{DAILY_BONUS})"
        )
    
    # Show dashboard
    await show_dashboard(update, context)

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
    
    # First check user's membership
    is_member = await check_membership(user_id, context)
    if not is_member:
        await query.message.edit_text(
            "❌ You must be a member of our channel and group to withdraw!\n"
            "Please join and try again.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
        )
        return ConversationHandler.END
    
    # Check referrals' membership
    all_members, not_in_channel = await verify_referrals_membership(user_id, context)
    if not all_members:
        referral_list = "\n".join([f"• User ID: {uid}" for uid in not_in_channel])
        await query.message.edit_text(
            "❌ Some of your referrals are not in the channel/group!\n\n"
            "The following referrals need to join:\n"
            f"{referral_list}\n\n"
            "Please ask them to join before withdrawing.",
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
    balance = user_balances.get(user_id, 0)
    if balance < MIN_WITHDRAWAL:
        await query.message.edit_text(
            f"❌ You need at least {MIN_WITHDRAWAL} points (₦{MIN_WITHDRAWAL}) to withdraw.\n"
            f"Your current balance: {balance} points (₦{balance})",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])
        )
        return ConversationHandler.END
    
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
        escaped_code = escape_markdown(code)

        message = (
            f"✅ Generated new coupon code:\n\n"
            f"Code: `{escaped_code}`\n"
            f"Amount: ₦{amount}\n"
            f"Expires: {escape_markdown(expiration_time.strftime('%Y-%m-%d %H:%M:%S'))}\n\n"
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
    """Process weekly rewards for top 5 referrers"""
    global last_weekly_reward
    current_time = datetime.now()
    
    # Check if a week has passed
    if (current_time - last_weekly_reward).days >= 7:
        # Get top 5 referrers
        top_referrers = sorted(referrals.items(), key=lambda x: len(x[1]), reverse=True)[:5]
        
        # Reward each top referrer
        for user_id, _ in top_referrers:
            user_balances[user_id] = user_balances.get(user_id, 0) + TOP_REFERRER_BONUS
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🎉 Congratulations! You're one of our top 5 referrers!\n"
                         f"You've earned ₦{TOP_REFERRER_BONUS} as a weekly reward!"
                )
            except Exception as e:
                print(f"Failed to send top referrer notification: {e}")
        
        # Announce in channel
        if top_referrers:
            try:
                message = "🏆 Weekly Top Referrers Awarded!\n\n"
                for i, (user_id, referred) in enumerate(top_referrers, 1):
                    try:
                        user = await context.bot.get_chat(user_id)
                        name = user.first_name
                        message += f"{i}. {name}: {len(referred)} referrals\n"
                    except:
                        message += f"{i}. User {user_id}: {len(referred)} referrals\n"
                
                message += f"\nEach winner received ₦{TOP_REFERRER_BONUS}! 🎁"
                
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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle normal text messages"""
    if not update.message or not update.message.text:
        return
        
    user = update.effective_user
    
    # Check if user has pending CAPTCHA
    if user.id in user_captcha:
        is_verified = await verify_captcha(update.message.text, user.id)
        if not is_verified:
            remaining_attempts = MAX_CAPTCHA_ATTEMPTS - user_captcha.get(user.id, {}).get('attempts', 0)
            if remaining_attempts > 0:
                await update.message.reply_text(
                    f"❌ Wrong code! You have {remaining_attempts} attempts remaining.\n"
                    "Try again or click Generate New CAPTCHA for a new code."
                )
            else:
                await update.message.reply_text(
                    "❌ Too many failed attempts. Please start over with /start"
                )
                if user.id in user_captcha:
                    del user_captcha[user.id]
            return
        
        await update.message.reply_text("✅ CAPTCHA verified successfully!")
        await show_dashboard(update, context)
        return
    
    # Check membership first
    is_member = await check_membership(user.id, context)
    if not is_member:
        await show_join_message(update, context)
        return
    
    # Process chat reward
    today = datetime.now().date()
    if user.id not in last_chat_reward or last_chat_reward[user.id] != today:
        # Reset daily counts if it's a new day
        last_chat_reward[user.id] = today
        daily_chat_count[user.id] = 0
    
    # Check if user hasn't reached daily chat reward limit
    if daily_chat_count[user.id] < MAX_DAILY_CHAT_REWARD:
        daily_chat_count[user.id] += 1
        user_balances[user.id] = user_balances.get(user.id, 0) + CHAT_REWARD

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    # Handle CAPTCHA button first
    if query.data == 'new_captcha':
        await handle_new_captcha(update, context)
        return

    # Handle verification button next
    if query.data == 'verify_membership':
        await handle_verify_membership(update, context)
        return

    # Rest of the button handlers...