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
BOT_USERNAME = "sub9ja_bot"

# Channel and Group IDs
CHANNEL_USERNAME = "latestinfoult"
GROUP_USERNAME = "-1002250504941"  # Updated with correct group ID
REQUIRED_CHANNEL = f"@{CHANNEL_USERNAME}"
REQUIRED_GROUP = f"https://t.me/+aeseN6uPGikzMDM0"  # Keep invite link for button

# Constants
WELCOME_BONUS = 100  # ₦100
REFERRAL_BONUS = 80  # Changed from 70 to 80
DAILY_BONUS = 25  # ₦25
MIN_WITHDRAWAL = 500  # ₦500 minimum withdrawal
MAX_WITHDRAWAL = 1000  # ₦1000 maximum withdrawal
LEAVE_PENALTY = 200  # ₦200 penalty for leaving channel/group
CHAT_REWARD = 1  # ₦1 per chat message
MAX_DAILY_CHAT_REWARD = 50  # Maximum ₦50 from chat per day

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

# Conversation states
(
    WITHDRAWAL_AMOUNT,
    ACCOUNT_NAME,
    BANK_NAME,
    ACCOUNT_NUMBER,
    PAYMENT_SCREENSHOT,  # New state for payment screenshot
) = range(5)

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
            InlineKeyboardButton("🎯 Get Link", callback_data='get_link'),
            InlineKeyboardButton("💸 Withdraw", callback_data='withdraw')
        ],
        [InlineKeyboardButton("📅 Daily Bonus", callback_data='daily_bonus')]
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
    
    # Handle both message and callback query updates
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Initialize verified status if new user
    if user.id not in user_verified_status:
        user_verified_status[user.id] = False
    
    is_existing_user = user.id in user_balances
    
    # Check if user is member of both channel and group
    is_member = await check_membership(user.id, context)
    if not is_member:
        # Store referral info if this is a referred user
        if context.args and len(context.args) > 0:
            referrer_id = int(context.args[0])
            if referrer_id != user.id:
                pending_referrals[user.id] = referrer_id
        
        if is_existing_user:
            await update.message.reply_text(
                f"👋 Welcome back {user.first_name}!\n"
                "⚠️ Please join our channel and group to continue using the bot."
            )
        await show_join_message(update, context)
        return
    
    # Handle new users
    if not is_existing_user:
        user_balances[user.id] = WELCOME_BONUS  # Welcome bonus
        referrals[user.id] = set()
        await update.message.reply_text(
            f"🎉 Welcome! You've received {WELCOME_BONUS} points (₦{WELCOME_BONUS}) as a welcome bonus!"
        )
    else:
        # Welcome back message for existing users
        await update.message.reply_text(
            f"👋 Welcome back {user.first_name}!\n"
            "You've been successfully verified. Here's your dashboard:"
        )
    
    # Check for daily sign-in bonus
    daily_bonus_earned = await check_and_credit_daily_bonus(user.id)
    if daily_bonus_earned:
        await update.message.reply_text(
            f"📅 Daily Sign-in Bonus!\nYou've earned {DAILY_BONUS} points (₦{DAILY_BONUS})"
        )

    # Show dashboard
    await show_dashboard(update, context)

async def can_withdraw_today(user_id: int) -> bool:
    today = datetime.now().date()
    last_date = last_withdrawal.get(user_id)
    return last_date is None or last_date < today

WITHDRAWAL_AMOUNT = 3  # Add this near other conversation states

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if query.data == 'check_membership':
        is_member = await check_membership(user_id, context)
        if is_member:
            await query.answer("✅ Membership verified!")
            # Show dashboard after verification
            await show_dashboard(update, context)
        else:
            await query.answer("❌ Please join both the channel and group!")
            return

    # Check membership for all other actions
    is_member = await check_membership(user_id, context)
    if not is_member:
        await query.answer("❌ Please join our channel and group first!")
        await show_join_message(query.message, context)
        return

    if query.data == 'back_to_menu':
        await query.answer("🔙 Returning to main menu...")
        await show_dashboard(update, context)
        return
    
    if query.data == 'my_referrals':
        ref_count = len(referrals.get(user_id, set()))
        await query.answer()
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
        await query.message.edit_text(
            f"You have {ref_count} referrals! 👥\n"
            f"Total earnings: {ref_count * REFERRAL_BONUS} points (₦{ref_count * REFERRAL_BONUS})",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == 'balance':
        balance = user_balances.get(user_id, 0)
        await query.answer()
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
        await query.message.edit_text(
            f"Your current balance: {balance} points (₦{balance}) 💰\n"
            f"You can withdraw once you reach {MIN_WITHDRAWAL} points (₦{MIN_WITHDRAWAL})!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == 'get_link':
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        await query.answer()
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
        await query.message.edit_text(
            f"Here's your referral link: {link}\n"
            f"Share this with your friends to earn points! 🎯\n"
            f"You'll get {REFERRAL_BONUS} points (₦{REFERRAL_BONUS}) for each friend who joins!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == 'withdraw':
        balance = user_balances.get(user_id, 0)
        
        # Check daily withdrawal limit
        if not await can_withdraw_today(user_id):
            await query.answer()
            tomorrow = datetime.now() + timedelta(days=1)
            tomorrow = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
            time_until = tomorrow - datetime.now()
            hours = int(time_until.total_seconds() // 3600)
            minutes = int((time_until.total_seconds() % 3600) // 60)
            
            keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
            await query.message.edit_text(
                f"❌ You can only withdraw once per day!\n"
                f"Next withdrawal available in {hours}h {minutes}m ⏳",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        if balance < MIN_WITHDRAWAL:
            await query.answer()
            keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
            await query.message.edit_text(
                f"❌ You need at least {MIN_WITHDRAWAL} points (₦{MIN_WITHDRAWAL}) to withdraw.\n"
                f"Your current balance: {balance} points (₦{balance})",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        # Start withdrawal process with amount input
        user_withdrawal_state[user_id] = {'stage': 'withdrawal_amount'}
        await query.answer()
        max_allowed = min(balance, MAX_WITHDRAWAL)  # Can't withdraw more than balance or max limit
        
        keyboard = [[InlineKeyboardButton("🔙 Cancel", callback_data='back_to_menu')]]
        await query.message.edit_text(
            f"💰 Enter withdrawal amount:\n\n"
            f"Minimum: ₦{MIN_WITHDRAWAL}\n"
            f"Maximum: ₦{max_allowed}\n"
            f"Your balance: ₦{balance}\n\n"
            f"Please enter an amount between ₦{MIN_WITHDRAWAL} and ₦{max_allowed}:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WITHDRAWAL_AMOUNT

    elif query.data == 'daily_bonus':
        daily_bonus_earned = await check_and_credit_daily_bonus(user_id)
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
        if daily_bonus_earned:
            await query.answer(f"✅ You earned {DAILY_BONUS} points (₦{DAILY_BONUS})!")
            await query.message.edit_text(
                f"📅 Daily Sign-in Bonus!\nYou've earned {DAILY_BONUS} points (₦{DAILY_BONUS})",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.answer("❌ You already claimed your daily bonus today!")
            await query.message.edit_text(
                "You've already claimed your daily bonus today.\nCome back tomorrow! 📅",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return

async def handle_withdrawal_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    amount_text = update.message.text.strip()
    
    try:
        amount = int(amount_text)
        balance = user_balances.get(user_id, 0)
        max_allowed = min(balance, MAX_WITHDRAWAL)
        
        if amount < MIN_WITHDRAWAL:
            await update.message.reply_text(
                f"❌ Minimum withdrawal amount is ₦{MIN_WITHDRAWAL}!\n"
                f"Please enter a larger amount:"
            )
            return WITHDRAWAL_AMOUNT
            
        if amount > max_allowed:
            await update.message.reply_text(
                f"❌ Maximum withdrawal amount is ₦{max_allowed}!\n"
                f"Please enter a smaller amount:"
            )
            return WITHDRAWAL_AMOUNT
            
        # Store amount and continue with account name
        user_withdrawal_state[user_id].update({
            'stage': 'account_name',
            'amount': amount
        })
        
        await update.message.reply_text(
            "Please enter your Account Name (as shown in your bank):"
        )
        return ACCOUNT_NAME
        
    except ValueError:
        await update.message.reply_text(
            "❌ Please enter a valid number!\n"
            f"Enter an amount between ₦{MIN_WITHDRAWAL} and ₦{max_allowed}:"
        )
        return WITHDRAWAL_AMOUNT

async def handle_account_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    account_name = update.message.text.strip()
    
    if len(account_name) < 3:
        await update.message.reply_text(
            "❌ Please enter a valid account name!"
        )
        return ACCOUNT_NAME
    
    # Store account name and show bank selection
    user_withdrawal_state[user_id]['account_name'] = account_name
    keyboard = [[InlineKeyboardButton(bank, callback_data=f'bank_{bank}')] 
                for bank in BANKS]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Please select your bank:",
        reply_markup=reply_markup
    )
    return BANK_NAME

async def handle_bank_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    bank = query.data.replace('bank_', '')
    
    if bank not in BANKS:
        await query.answer()
        await query.message.reply_text("❌ Invalid bank selection. Please try again.")
        return BANK_NAME
    
    # Store bank name and ask for account number
    user_withdrawal_state[user_id]['bank'] = bank
    await query.answer()
    await query.message.reply_text(
        "Please enter your Account Number:"
    )
    return ACCOUNT_NUMBER

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

async def handle_account_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    account_number = update.message.text.strip()
    
    # Validate account number (10 digits for Nigerian banks)
    if not account_number.isdigit() or len(account_number) != 10:
        await update.message.reply_text(
            "❌ Invalid account number! Please enter a valid 10-digit account number."
        )
        return ACCOUNT_NUMBER
    
    # Process withdrawal
    user_data = user_withdrawal_state[user_id]
    withdrawal_amount = user_data.get('amount', 0)
    
    # Store account number
    user_data['account_number'] = account_number
    
    # Update user balance and last withdrawal date
    user_balances[user_id] = user_balances.get(user_id, 0) - withdrawal_amount
    last_withdrawal[user_id] = datetime.now().date()
    
    # Send withdrawal notification to admin only
    await notify_withdrawal_request(user_id, withdrawal_amount, user_data, context)
    
    # Show confirmation to user
    keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
    await update.message.reply_text(
        f"✅ Withdrawal request successful!\n\n"
        f"Account Details:\n"
        f"Name: {user_data['account_name']}\n"
        f"Bank: {user_data['bank']}\n"
        f"Account Number: {account_number}\n"
        f"Amount: ₦{withdrawal_amount}\n"
        f"Remaining balance: ₦{user_balances[user_id]}\n\n"
        f"Your payment will be processed within 24 hours!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return ConversationHandler.END

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
        
        # Clear pending payment
        del context.user_data['pending_payment_user']
        
        await update.message.reply_text(f"✅ Payment marked as completed for user {target_user_id}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    
    return ConversationHandler.END

async def handle_reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        
        # Refund the points
        if target_user_id in user_withdrawal_state:
            refund_amount = user_withdrawal_state[target_user_id].get('amount', 0)
            user_balances[target_user_id] = user_balances.get(target_user_id, 0) + refund_amount
            del user_withdrawal_state[target_user_id]
        
        # Notify user
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"❌ Your withdrawal has been rejected.\nReason: {reason}\nYour points have been refunded."
        )
        
        await update.message.reply_text(f"✅ Rejected withdrawal for user {target_user_id}")
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
        
        await update.message.reply_text(
            f"✅ Generated new coupon code:\n\n"
            f"Code: `{code}`\n"
            f"Amount: ₦{amount}\n"
            f"Expires: {expiration_time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"Users can redeem this code using:\n"
            f"/redeem {code}",
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

async def get_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Check if user is member of both channel and group
    is_member = await check_membership(user.id, context)
    if not is_member:
        await show_join_message(update, context)
        return
    
    # Get user statistics
    balance = user_balances.get(user.id, 0)
    ref_count = len(referrals.get(user.id, set()))
    total_earnings = ref_count * REFERRAL_BONUS
    last_signin_date = last_signin.get(user.id, None)
    
    # Calculate next daily bonus time
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
        f"ID: {user.id}\n"
        f"Name: {user.first_name} {user.last_name if user.last_name else ''}\n"
        f"Username: @{user.username if user.username else 'None'}\n\n"
        
        f"💰 Balance & Earnings\n"
        f"───────────────\n"
        f"Current Balance: {balance} points (₦{balance})\n"
        f"Total Referrals: {ref_count}\n"
        f"Referral Earnings: {total_earnings} points (₦{total_earnings})\n\n"
        
        f"📊 Statistics\n"
        f"───────────────\n"
        f"Welcome Bonus: {WELCOME_BONUS} points (₦{WELCOME_BONUS})\n"
        f"Daily Bonus: {DAILY_BONUS} points (₦{DAILY_BONUS})\n"
        f"Next Daily Bonus: {next_bonus}\n"
        f"Min. Withdrawal: {MIN_WITHDRAWAL} points (₦{MIN_WITHDRAWAL})"
    )
    
    await update.message.reply_text(info_message)

async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to get chat ID"""
    user = update.effective_user
    
    if not await is_admin(user.id):
        await update.message.reply_text("❌ This command is only for admins!")
        return
        
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"Current chat ID: {chat_id}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle normal text messages"""
    if not update.message or not update.message.text:
        return
        
    user = update.effective_user
    
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
    
    return  # Just let the message through without auto-reply

def main():
    token = os.getenv('BOT_TOKEN')
    port = int(os.getenv('PORT', '8443'))
    webhook_url = os.getenv('WEBHOOK_URL')
    heroku_app_name = os.getenv('HEROKU_APP_NAME')
    secret = os.getenv('WEBHOOK_SECRET', 'your-256-bit-secret-token')  # Add secret token env var
    
    if not token:
        raise ValueError("No BOT_TOKEN found in environment variables")
    
    application = Application.builder().token(token).build()
    
    # Create conversation handler for withdrawal process
    withdrawal_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern='^withdraw$')],
        states={
            WITHDRAWAL_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_withdrawal_amount)],
            ACCOUNT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_account_name)],
            BANK_NAME: [CallbackQueryHandler(handle_bank_selection, pattern='^bank_')],
            ACCOUNT_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_account_number)]
        },
        fallbacks=[
            CommandHandler('start', start),
            CallbackQueryHandler(button_handler)
        ],
        name="withdrawal_conversation",
        persistent=False
    )
    
    # Create conversation handler for payment screenshot
    payment_handler = ConversationHandler(
        entry_points=[CommandHandler("paid", handle_paid_command)],
        states={
            PAYMENT_SCREENSHOT: [MessageHandler(filters.PHOTO, handle_payment_screenshot)]
        },
        fallbacks=[CommandHandler('start', start)],
        name="payment_screenshot_conversation",
        persistent=False
    )
    
    # Add all handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("info", get_user_info))
    application.add_handler(CommandHandler("chatid", get_chat_id))  # Add new command
    application.add_handler(CommandHandler("generate", handle_generate_command))  # Add generate command
    application.add_handler(CommandHandler("redeem", handle_redeem_command))     # Add redeem command
    application.add_handler(withdrawal_handler)
    application.add_handler(payment_handler)  # Add the new payment handler
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(CommandHandler("reject", handle_reject_command))
    application.add_handler(CommandHandler("add", handle_add_command))
    application.add_handler(CommandHandler("deduct", handle_deduct_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))  # Add message handler
    
    # Set up webhook with proper error handling and configuration
    if webhook_url:
        # Use provided webhook URL if available
        webhook_path = webhook_url.split('/')[-1]
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=webhook_path,
            webhook_url=webhook_url,
            drop_pending_updates=True,
            secret_token=secret,  # Use proper secret token
            allowed_updates=[
                "message",
                "callback_query",
                "chat_member"
            ]
        )
    elif heroku_app_name:
        # Fallback to constructing URL from Heroku app name
        webhook_url = f"https://{heroku_app_name}.herokuapp.com/{token}"
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=token,
            webhook_url=webhook_url,
            drop_pending_updates=True,
            secret_token=secret,  # Use proper secret token
            allowed_updates=[
                "message",
                "callback_query",
                "chat_member"
            ]
        )
    else:
        raise ValueError("Either WEBHOOK_URL or HEROKU_APP_NAME must be set in environment variables")

if __name__ == '__main__':
    main()