from sqlalchemy import create_engine, Column, Integer, BigInteger, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True)
    username = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    balance = Column(Float, default=0.0)
    is_verified = Column(Boolean, default=False)
    joined_date = Column(DateTime, default=datetime.now)
    activities = relationship("Activity", back_populates="user")
    transactions = relationship("Transaction", back_populates="user")

class Activity(Base):
    __tablename__ = 'activities'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'))
    activity_type = Column(String)  # e.g., "verification", "withdrawal", "referral"
    description = Column(Text)
    amount = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=datetime.now)
    user = relationship("User", back_populates="activities")

class Transaction(Base):
    __tablename__ = 'transactions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'))
    type = Column(String)  # "withdrawal", "referral_bonus", etc.
    amount = Column(Float)
    status = Column(String)  # "pending", "completed", "failed"
    timestamp = Column(DateTime, default=datetime.now)
    user = relationship("User", back_populates="transactions")

def log_activity(session, user_id: int, activity_type: str, description: str, amount: float = None):
    """Log user activity to the database"""
    try:
        activity = Activity(
            user_id=user_id,
            activity_type=activity_type,
            description=description,
            amount=amount
        )
        session.add(activity)
        session.commit()
    except Exception as e:
        print(f"Error logging activity: {e}")
        session.rollback()

# Database initialization
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

engine = create_engine(DATABASE_URL or 'sqlite:///bot.db')
Session = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(engine)

if __name__ == "__main__":
    print("Creating database tables...")
    init_db()
    print("Database tables created successfully!")