# Database Schema & Models

**Last Updated:** 2025-01-13

Complete database schema for Cradler platform.

---

## Core Tables

### users
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    api_key VARCHAR(64) UNIQUE,
    role VARCHAR(20) DEFAULT 'user',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**Fields:**
- `id` - UUID primary key
- `email` - Unique user email
- `password_hash` - bcrypt hashed password
- `api_key` - API key for programmatic access
- `role` - User role: 'user' or 'admin'

---

### scrapers
```sql
CREATE TABLE scrapers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    name VARCHAR(255) NOT NULL,
    target_url TEXT NOT NULL,
    target_domain VARCHAR(255),
    scraping_config JSONB NOT NULL,
    schedule_cron VARCHAR(100),
    status VARCHAR(20) DEFAULT 'active',
    last_run_at TIMESTAMP,
    last_success_at TIMESTAMP,
    page_hash VARCHAR(64),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**Fields:**
- `id` - UUID primary key
- `user_id` - Foreign key to users table
- `name` - User-defined scraper name
- `target_url` - URL to scrape
- `target_domain` - Extracted domain from URL
- `scraping_config` - JSONB containing configuration and generated code
- `schedule_cron` - Cron expression for scheduled runs
- `status` - Status: 'inactive', 'generating', 'active', 'failed', 'paused', 'maintenance'
- `last_run_at` - Timestamp of last execution
- `last_success_at` - Timestamp of last successful run
- `page_hash` - SHA-256 hash for change detection

**scraping_config JSONB Structure:**
```json
{
  "data_fields": ["title", "price", "rating"],
  "special_requirements": "Extract all products",
  "generated_code": "from botasaurus import browser...",
  "reasoning_log": [
    {
      "iteration": 1,
      "type": "reasoning.text",
      "text": "I need to navigate...",
      "format": "anthropic-claude-v1"
    }
  ],
  "test_results": {
    "success": true,
    "records_scraped": 20,
    "execution_time": 3.5
  },
  "tool_calls": [...],
  "iterations": 8,
  "final_message": "Code generation completed",
  "generation_completed_at": "2025-01-13T14:45:39.000Z"
}
```

---

### scraping_runs
```sql
CREATE TABLE scraping_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scraper_id UUID REFERENCES scrapers(id),
    status VARCHAR(20),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    records_scraped INTEGER DEFAULT 0,
    error_message TEXT,
    output_url TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Fields:**
- `id` - UUID primary key
- `scraper_id` - Foreign key to scrapers table
- `status` - Run status: 'queued', 'running', 'success', 'failed'
- `started_at` - Execution start time
- `completed_at` - Execution end time
- `records_scraped` - Number of records extracted
- `error_message` - Error details if failed
- `output_url` - S3/MinIO URL for scraped data

---

### chat_sessions
```sql
CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    scraper_id UUID REFERENCES scrapers(id),
    messages JSONB NOT NULL DEFAULT '[]',
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**Fields:**
- `id` - UUID primary key
- `user_id` - Foreign key to users table
- `scraper_id` - Optional foreign key to scrapers (created from chat)
- `messages` - JSONB array of chat messages
- `status` - Session status: 'active', 'completed', 'abandoned'

**messages JSONB Structure:**
```json
[
  {
    "role": "user",
    "content": "I want to scrape books.toscrape.com",
    "timestamp": "2025-01-13T14:30:00.000Z"
  },
  {
    "role": "assistant",
    "content": "What data fields do you need?",
    "timestamp": "2025-01-13T14:30:05.000Z"
  }
]
```

---

### chat_messages
```sql
CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES chat_sessions(id),
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Fields:**
- `id` - UUID primary key
- `session_id` - Foreign key to chat_sessions
- `role` - Message role: 'user', 'assistant', 'system'
- `content` - Message text

---

### scraper_templates (Future)
```sql
CREATE TABLE scraper_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform VARCHAR(50),
    selector_patterns JSONB,
    api_patterns JSONB,
    common_issues JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**Purpose:** Platform-specific patterns (Shopify, WooCommerce) for template-based scraping.

**Fields:**
- `platform` - Platform name: 'shopify', 'woocommerce', 'magento', 'custom'
- `selector_patterns` - Common CSS selectors for platform
- `api_patterns` - API endpoint patterns
- `common_issues` - Known anti-bot measures

---

### scraping_knowledge (Future)
```sql
CREATE TABLE scraping_knowledge (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    embedding vector(1536),
    content TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX ON scraping_knowledge USING ivfflat (embedding vector_l2_ops);
```

**Purpose:** Vector storage for RAG (scraping patterns, solutions).

**Requires:** pgvector extension

**Fields:**
- `embedding` - Vector embedding (1536 dimensions for OpenAI)
- `content` - Text content
- `metadata` - Type, platform, category information

---

## SQLAlchemy Models

### User Model
```python
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    api_key = Column(String(64), unique=True)
    role = Column(String(20), default="user")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
```

### Scraper Model
```python
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB

class Scraper(Base):
    __tablename__ = "scrapers"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    name = Column(String(255), nullable=False)
    target_url = Column(Text, nullable=False)
    target_domain = Column(String(255))
    scraping_config = Column(JSONB, nullable=False, server_default='{}')
    schedule_cron = Column(String(100))
    status = Column(String(20), default="active")
    last_run_at = Column(DateTime)
    last_success_at = Column(DateTime)
    page_hash = Column(String(64))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
```

### ScrapingRun Model
```python
class ScrapingRun(Base):
    __tablename__ = "scraping_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    scraper_id = Column(UUID(as_uuid=True), ForeignKey("scrapers.id"))
    status = Column(String(20))
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    records_scraped = Column(Integer, default=0)
    error_message = Column(Text)
    output_url = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
```

### ChatSession Model
```python
class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    scraper_id = Column(UUID(as_uuid=True), ForeignKey("scrapers.id"))
    messages = Column(JSONB, nullable=False, server_default='[]')
    status = Column(String(20), default="active")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
```

### ChatMessage Model
```python
class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"))
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
```

---

## Indexes

### Performance Indexes
```sql
-- User lookups by email
CREATE INDEX idx_users_email ON users(email);

-- Scraper lookups by user
CREATE INDEX idx_scrapers_user_id ON scrapers(user_id);
CREATE INDEX idx_scrapers_status ON scrapers(status);

-- Runs by scraper
CREATE INDEX idx_scraping_runs_scraper_id ON scraping_runs(scraper_id);
CREATE INDEX idx_scraping_runs_status ON scraping_runs(status);

-- Chat sessions by user
CREATE INDEX idx_chat_sessions_user_id ON chat_sessions(user_id);

-- Vector similarity search (future)
CREATE INDEX idx_scraping_knowledge_embedding ON scraping_knowledge
USING ivfflat (embedding vector_l2_ops);
```

---

## Database Connection

### Configuration
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql+asyncpg://user:pass@localhost/cradler"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)
```

### Dependency Injection
```python
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

---

## Migration Notes

### pgvector Extension
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### UUID Generation
```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- OR use gen_random_uuid() (PostgreSQL 13+)
```

---

## Data Retention Policies

- **Scraped Data:** 120 days (stored in S3/MinIO)
- **Chat Sessions:** Indefinite (user can delete)
- **Scraping Runs:** 90 days metadata, 120 days data files
- **User Data:** Until account deletion
