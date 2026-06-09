"""Add cascade deletes to foreign keys

Revision ID: 002
Revises: 001
Create Date: 2025-01-18

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade():
    """
    Add CASCADE and SET NULL to foreign key constraints

    - chat_sessions.scraper_id -> SET NULL (chat can exist without scraper)
    - scraping_runs.scraper_id -> CASCADE (run doesn't make sense without scraper)
    """
    # Drop existing foreign key constraints
    op.drop_constraint('chat_sessions_scraper_id_fkey', 'chat_sessions', type_='foreignkey')
    op.drop_constraint('scraping_runs_scraper_id_fkey', 'scraping_runs', type_='foreignkey')

    # Re-create with proper ON DELETE behavior
    op.create_foreign_key(
        'chat_sessions_scraper_id_fkey',
        'chat_sessions',
        'scrapers',
        ['scraper_id'],
        ['id'],
        ondelete='SET NULL'
    )

    op.create_foreign_key(
        'scraping_runs_scraper_id_fkey',
        'scraping_runs',
        'scrapers',
        ['scraper_id'],
        ['id'],
        ondelete='CASCADE'
    )


def downgrade():
    """Revert to previous foreign key constraints without cascade"""
    # Drop the new constraints
    op.drop_constraint('chat_sessions_scraper_id_fkey', 'chat_sessions', type_='foreignkey')
    op.drop_constraint('scraping_runs_scraper_id_fkey', 'scraping_runs', type_='foreignkey')

    # Re-create without ON DELETE
    op.create_foreign_key(
        'chat_sessions_scraper_id_fkey',
        'chat_sessions',
        'scrapers',
        ['scraper_id'],
        ['id']
    )

    op.create_foreign_key(
        'scraping_runs_scraper_id_fkey',
        'scraping_runs',
        'scrapers',
        ['scraper_id'],
        ['id']
    )
