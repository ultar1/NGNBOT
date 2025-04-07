"""Initial database migration

This script creates all the necessary tables for the bot to function.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from bot import Base, User, Referral, Withdrawal, Coupon, CouponUsage
import os

def upgrade():
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    # Create engine and tables
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    
    # Create session
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Add any initial data here if needed
        pass
    finally:
        session.close()

def downgrade():
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    # Create engine
    engine = create_engine(database_url)
    
    # Drop all tables
    Base.metadata.drop_all(engine)

if __name__ == "__main__":
    upgrade()