from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from config import settings

# Используем пул соединений вместо NullPool — держим TCP/TLS соединения открытыми.
# Это критично для удалённого Supabase: экономим 200-500ms на каждом запросе.
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def get_db():
    """Dependency для FastAPI — инжектирует async сессию в роутеры."""
    async with AsyncSessionLocal() as session:
        yield session
