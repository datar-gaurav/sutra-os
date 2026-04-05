#!/bin/bash
set -e

echo "═══════════════════════════════════════════════"
echo "  🚀 Sutra Backend — Starting Up"
echo "═══════════════════════════════════════════════"

# ── Wait for PostgreSQL ──────────────────────────
echo "⏳ Waiting for PostgreSQL..."
MAX_RETRIES=30
RETRY=0
until python -c "
import asyncio, sys
async def check():
    try:
        import asyncpg
        # Parse the URL: postgresql+asyncpg://user:pass@host:port/db
        url = '$DATABASE_URL'.replace('postgresql+asyncpg://', 'postgresql://')
        conn = await asyncpg.connect(url)
        await conn.close()
        print('  ✅ PostgreSQL is ready')
    except Exception as e:
        print(f'  ⏳ PostgreSQL not ready: {e}', file=sys.stderr)
        sys.exit(1)
asyncio.run(check())
" 2>/dev/null; do
    RETRY=$((RETRY + 1))
    if [ $RETRY -ge $MAX_RETRIES ]; then
        echo "  ❌ PostgreSQL did not become ready in time"
        exit 1
    fi
    sleep 2
done

# ── Wait for Redis ───────────────────────────────
echo "⏳ Waiting for Redis..."
RETRY=0
until python -c "
import redis, sys
try:
    r = redis.from_url('$REDIS_URL')
    r.ping()
    print('  ✅ Redis is ready')
except Exception as e:
    print(f'  ⏳ Redis not ready: {e}')
    sys.exit(1)
" 2>/dev/null; do
    RETRY=$((RETRY + 1))
    if [ $RETRY -ge $MAX_RETRIES ]; then
        echo "  ❌ Redis did not become ready in time"
        exit 1
    fi
    sleep 2
done

# ── Run database migrations / table creation ─────
echo "📦 Initializing database tables..."
python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.models.base import Base

async def init_db():
    engine = create_async_engine('$DATABASE_URL')
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print('  ✅ Database tables created/verified')

asyncio.run(init_db())
"

echo ""
echo "═══════════════════════════════════════════════"
echo "  ⚡ Starting Sutra API Server"
echo "  📍 http://0.0.0.0:8000"
echo "  📚 Docs: http://0.0.0.0:8000/docs"
echo "═══════════════════════════════════════════════"
echo ""

# ── Start the application ────────────────────────
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 "$@"
