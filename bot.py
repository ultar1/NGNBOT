import os
import random
import string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMemberUpdated
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters, ConversationHandler, ChatMemberHandler
from telegram.constants import ChatMemberStatus
from dotenv import load_dotenv
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Table, MetaData, Boolean
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.sql import func

# Load environment variables
load_dotenv()

# Database setup
DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL is None:
    raise ValueError("DATABASE_URL environment variable is not set")

# Fix Heroku's postgres:// URLs to postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Configure SQLAlchemy engine with proper connection pooling
engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,  # Recycle connections every 30 minutes
    pool_pre_ping=True  # Enable connection health checks
)
Base = declarative_base()
Session = sessionmaker(bind=engine)

# Create a connection pool manager
def get_db_session():
    session = Session()
    try:
        yield session
    finally:
        session.close()

# Database Models
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    balance = Column(Float, default=0)
    last_signin = Column(DateTime)
    last_withdrawal = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    
    referrals = relationship('Referral', back_populates='referrer')
    withdrawals = relationship('Withdrawal', back_populates='user')

class Referral(Base):
    __tablename__ = 'referrals'
    id = Column(Integer, primary_key=True)
    referrer_id = Column(Integer, ForeignKey('users.telegram_id'))
    referred_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    
    referrer = relationship('User', back_populates='referrals')

class Withdrawal(Base):
    __tablename__ = 'withdrawals'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.telegram_id'))
    amount = Column(Float)
    account_name = Column(String)
    bank_name = Column(String)
    account_number = Column(String)
    status = Column(String)  # 'pending', 'completed', 'rejected'
    created_at = Column(DateTime, server_default=func.now())
    
    user = relationship('User', back_populates='withdrawals')

class Coupon(Base):
    __tablename__ = 'coupons'
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True)
    amount = Column(Float)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    used_by = relationship('CouponUsage', back_populates='coupon')

class CouponUsage(Base):
    __tablename__ = 'coupon_usages'
    id = Column(Integer, primary_key=True)
    coupon_id = Column(Integer, ForeignKey('coupons.id'))
    user_id = Column(Integer)
    used_at = Column(DateTime, server_default=func.now())
    
    coupon = relationship('Coupon', back_populates='used_by')

# Create all tables
Base.metadata.create_all(engine)

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

# Database utility functions
def get_or_create_user(session, telegram_id):
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id, balance=0)
        session.add(user)
        session.commit()
    return user

def update_user_balance(session, telegram_id, amount):
    user = get_or_create_user(session, telegram_id)
    user.balance += amount
    session.commit()
    return user.balance

def get_user_balance(session, telegram_id):
    user = get_or_create_user(session, telegram_id)
    return user.balance

def add_referral(session, referrer_id, referred_id):
    referral = Referral(referrer_id=referrer_id, referred_id=referred_id)
    session.add(referral)
    session.commit()

def get_referral_count(session, referrer_id):
    return session.query(Referral).filter_by(referrer_id=referrer_id).count()

def check_and_credit_daily_bonus(session, user_id):
    user = get_or_create_user(session, user_id)
    today = datetime.now().date()
    
    if not user.last_signin or user.last_signin.date() < today:
        user.last_signin = datetime.now()
        user.balance += DAILY_BONUS
        session.commit()
        return True
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

        session = Session()
        try:
            user = get_or_create_user(session, user_id)
            is_existing_user = user.created_at is not None
            
            if not is_existing_user:
                await query.message.edit_text(
                    "✅ Verification Successful!\n\n"
                    f"🎁 You received ₦{WELCOME_BONUS} welcome bonus!\n"
                    "Loading your dashboard..."
                )
                update_user_balance(session, user_id, WELCOME_BONUS)
            
            # Check for daily bonus
            daily_bonus_earned = check_and_credit_daily_bonus(session, user_id)
            if daily_bonus_earned:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"📅 Daily Bonus!\nYou earned ₦{DAILY_BONUS} for logging in today!"
                )
            
            # Show dashboard
            await show_dashboard(update, context)
            
        finally:
            session.close()
            
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
    session = Session()
    try:
        balance = get_user_balance(session, user.id)
        ref_count = get_referral_count(session, user.id)
        
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
    finally:
        session.close()

async def handle_withdrawal_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = Session()
    try:
        user = get_or_create_user(session, user_id)
        balance = user.balance
        
        # Check if user can withdraw today
        if user.last_withdrawal and user.last_withdrawal.date() == datetime.now().date():
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
    finally:
        session.close()

async def handle_withdrawal_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    amount_text = update.message.text.strip()
    
    session = Session()
    try:
        amount = int(amount_text)
        user = get_or_create_user(session, user_id)
        balance = user.balance
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
            
        # Create pending withdrawal
        withdrawal = Withdrawal(
            user_id=user_id,
            amount=amount,
            status='pending'
        )
        session.add(withdrawal)
        session.commit()
        
        await update.message.reply_text(
            "Please enter your Account Name (as shown in your bank):"
        )
        return ACCOUNT_NAME
    finally:
        session.close()

async def handle_account_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    account_name = update.message.text.strip()
    
    session = Session()
    try:
        withdrawal = session.query(Withdrawal).filter_by(
            user_id=user_id,
            status='pending'
        ).order_by(Withdrawal.created_at.desc()).first()
        
        if withdrawal:
            withdrawal.account_name = account_name
            session.commit()
            
            # Show bank selection buttons
            keyboard = [[InlineKeyboardButton(bank, callback_data=f"bank_{bank}")] for bank in BANKS]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "Please select your bank:",
                reply_markup=reply_markup
            )
            return BANK_NAME
    finally:
        session.close()

async def handle_bank_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    selected_bank = query.data.replace('bank_', '')
    
    session = Session()
    try:
        withdrawal = session.query(Withdrawal).filter_by(
            user_id=user_id,
            status='pending'
        ).order_by(Withdrawal.created_at.desc()).first()
        
        if withdrawal:
            withdrawal.bank_name = selected_bank
            session.commit()
            
            await query.message.reply_text(
                "Please enter your Account Number:"
            )
            return ACCOUNT_NUMBER
    finally:
        session.close()

async def handle_account_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    account_number = update.message.text.strip()
    
    if not account_number.isdigit() or len(account_number) < 10:
        await update.message.reply_text(
            "❌ Invalid account number! Please enter a valid account number:"
        )
        return ACCOUNT_NUMBER
    
    session = Session()
    try:
        withdrawal = session.query(Withdrawal).filter_by(
            user_id=user_id,
            status='pending'
        ).order_by(Withdrawal.created_at.desc()).first()
        
        if withdrawal:
            withdrawal.account_number = account_number
            user = get_or_create_user(session, user_id)
            
            # Update user's balance and last withdrawal time
            user.balance -= withdrawal.amount
            user.last_withdrawal = datetime.now()
            
            # Update withdrawal status
            withdrawal.status = 'pending_admin'
            session.commit()
            
            # Notify admin
            admin_message = (
                "🔔 New Withdrawal Request!\n\n"
                f"User: @{update.effective_user.username}\n"
                f"Amount: ₦{withdrawal.amount}\n"
                f"Bank: {withdrawal.bank_name}\n"
                f"Account: {withdrawal.account_name}\n"
                f"Number: {withdrawal.account_number}"
            )
            
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_message,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Approve", callback_data=f"approve_withdrawal_{withdrawal.id}"),
                        InlineKeyboardButton("❌ Reject", callback_data=f"reject_withdrawal_{withdrawal.id}")
                    ]
                ])
            )
            
            await update.message.reply_text(
                "✅ Withdrawal request submitted!\n\n"
                "Your request is being processed.\n"
                "You will be notified once it's approved.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]
                ])
            )
            return ConversationHandler.END
    finally:
        session.close()

async def handle_referral_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.username or str(user_id)
    
    # Generate referral link
    bot_username = BOT_USERNAME
    referral_link = f"https://t.me/{bot_username}?start={user_id}"
    
    session = Session()
    try:
        ref_count = get_referral_count(session, user_id)
        earnings = ref_count * REFERRAL_BONUS
        
        await update.callback_query.message.edit_text(
            "🔗 Your Referral Link:\n\n"
            f"`{referral_link}`\n\n"
            f"👥 Your Referrals: {ref_count}\n"
            f"💰 Referral Earnings: ₦{earnings}\n\n"
            "Share this link with friends!\n"
            f"You earn ₦{REFERRAL_BONUS} for each verified referral.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]
            ])
        )
    finally:
        session.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message
    
    # Check if this is a referral
    if len(context.args) > 0:
        try:
            referrer_id = int(context.args[0])
            if referrer_id != user.id:  # Prevent self-referral
                session = Session()
                try:
                    # Check if user is new
                    existing_user = session.query(User).filter_by(telegram_id=user.id).first()
                    if not existing_user:
                        # Add referral
                        add_referral(session, referrer_id, user.id)
                        # Credit referrer
                        update_user_balance(session, referrer_id, REFERRAL_BONUS)
                        # Notify referrer
                        await context.bot.send_message(
                            chat_id=referrer_id,
                            text=f"🎉 New referral! You earned ₦{REFERRAL_BONUS}"
                        )
                finally:
                    session.close()
    
    # Welcome message
    keyboard = [
        [
            InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME}"),
            InlineKeyboardButton("👥 Join Group", url=REQUIRED_GROUP)
        ],
        [InlineKeyboardButton("✅ Verify Membership", callback_data='verify_membership')]
    ]
    
    await message.reply_text(
        f"👋 Welcome {user.first_name}!\n\n"
        "To start earning:\n"
        "1. Join our channel\n"
        "2. Join our group\n"
        "3. Click verify\n\n"
        "You'll get:\n"
        f"• ₦{WELCOME_BONUS} welcome bonus\n"
        f"• ₦{REFERRAL_BONUS} per referral\n"
        f"• ₦{DAILY_BONUS} daily login bonus",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Add at the end of file:
if __name__ == "__main__":
    app = Application.builder().token(os.getenv('BOT_TOKEN')).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_verify_membership, pattern="^verify_membership$"))
    app.add_handler(CallbackQueryHandler(handle_bank_selection, pattern="^bank_"))
    app.add_handler(CallbackQueryHandler(handle_referral_link, pattern="^get_link$"))
    
    # Add withdrawal conversation handler
    withdrawal_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_withdrawal_request, pattern="^withdraw$")],
        states={
            WITHDRAWAL_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_withdrawal_amount)],
            ACCOUNT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_account_name)],
            BANK_NAME: [CallbackQueryHandler(handle_bank_selection, pattern="^bank_")],
            ACCOUNT_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_account_number)]
        },
        fallbacks=[],
    )
    app.add_handler(withdrawal_conv)
    
    # Start the bot
    print("Bot is running...")
    app.run_polling()