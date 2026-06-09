"""Initial schema

Revision ID: 001
Revises:
Create Date: 2025-01-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('api_key', sa.String(length=64), nullable=True),
        sa.Column('role', sa.String(length=20), nullable=False, server_default='user'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_api_key'), 'users', ['api_key'], unique=True)

    # Create scrapers table
    op.create_table(
        'scrapers',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('target_url', sa.Text(), nullable=False),
        sa.Column('target_domain', sa.String(length=255), nullable=True),
        sa.Column('scraping_config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('schedule_cron', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('page_hash', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_scrapers_user_id'), 'scrapers', ['user_id'], unique=False)
    op.create_index(op.f('ix_scrapers_target_domain'), 'scrapers', ['target_domain'], unique=False)
    op.create_index(op.f('ix_scrapers_status'), 'scrapers', ['status'], unique=False)

    # Create scraping_runs table
    op.create_table(
        'scraping_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('scraper_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('records_scraped', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('output_url', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['scraper_id'], ['scrapers.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_scraping_runs_scraper_id'), 'scraping_runs', ['scraper_id'], unique=False)
    op.create_index(op.f('ix_scraping_runs_status'), 'scraping_runs', ['status'], unique=False)

    # Create scraper_templates table
    op.create_table(
        'scraper_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('platform', sa.String(length=50), nullable=False),
        sa.Column('selector_patterns', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('api_patterns', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('common_issues', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_scraper_templates_platform'), 'scraper_templates', ['platform'], unique=False)

    # Create scraping_knowledge table (for RAG - future use)
    op.create_table(
        'scraping_knowledge',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('embedding', Vector(1536), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    # Create vector similarity index
    op.execute(
        'CREATE INDEX ix_scraping_knowledge_embedding ON scraping_knowledge '
        'USING ivfflat (embedding vector_l2_ops) WITH (lists = 100)'
    )

    # Create chat_sessions table
    op.create_table(
        'chat_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('scraper_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('messages', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['scraper_id'], ['scrapers.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chat_sessions_user_id'), 'chat_sessions', ['user_id'], unique=False)
    op.create_index(op.f('ix_chat_sessions_scraper_id'), 'chat_sessions', ['scraper_id'], unique=False)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index(op.f('ix_chat_sessions_scraper_id'), table_name='chat_sessions')
    op.drop_index(op.f('ix_chat_sessions_user_id'), table_name='chat_sessions')
    op.drop_table('chat_sessions')

    op.execute('DROP INDEX IF EXISTS ix_scraping_knowledge_embedding')
    op.drop_table('scraping_knowledge')

    op.drop_index(op.f('ix_scraper_templates_platform'), table_name='scraper_templates')
    op.drop_table('scraper_templates')

    op.drop_index(op.f('ix_scraping_runs_status'), table_name='scraping_runs')
    op.drop_index(op.f('ix_scraping_runs_scraper_id'), table_name='scraping_runs')
    op.drop_table('scraping_runs')

    op.drop_index(op.f('ix_scrapers_status'), table_name='scrapers')
    op.drop_index(op.f('ix_scrapers_target_domain'), table_name='scrapers')
    op.drop_index(op.f('ix_scrapers_user_id'), table_name='scrapers')
    op.drop_table('scrapers')

    op.drop_index(op.f('ix_users_api_key'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')

    # Disable pgvector extension
    op.execute('DROP EXTENSION IF EXISTS vector')
