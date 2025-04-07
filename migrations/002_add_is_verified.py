"""Add is_verified column to users table

This migration adds the is_verified column to the users table.
"""

from sqlalchemy import create_engine, text
import os

def upgrade():
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    # Create engine
    engine = create_engine(database_url)
    
    # Add is_verified column
    with engine.connect() as connection:
        connection.execute(text("ALTER TABLE users ADD COLUMN is_verified BOOLEAN DEFAULT FALSE"))
        connection.commit()

def downgrade():
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    # Create engine
    engine = create_engine(database_url)
    
    # Remove is_verified column
    with engine.connect() as connection:
        connection.execute(text("ALTER TABLE users DROP COLUMN is_verified"))
        connection.commit()

if __name__ == "__main__":
    upgrade()