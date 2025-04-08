from sqlalchemy import BigInteger
from alembic import op

def upgrade():
    # Use raw SQL for PostgreSQL
    op.execute('ALTER TABLE users ALTER COLUMN telegram_id TYPE BIGINT')

def downgrade():
    # Only attempt to downgrade if all values fit within regular INTEGER
    op.execute('ALTER TABLE users ALTER COLUMN telegram_id TYPE INTEGER')