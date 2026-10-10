from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, BigInteger, Text, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from app.config import DATABASE_URL, DEFAULT_PREFIX

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class Base(DeclarativeBase):
    pass

class GuildConfig(Base):
    __tablename__ = "guild_configs"
    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    prefix: Mapped[str] = mapped_column(String(8), default=DEFAULT_PREFIX)
    welcome_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    welcome_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    welcome_message: Mapped[str] = mapped_column(Text, default="Welcome {user} to {server}!")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_guild_config(session: AsyncSession, guild_id: int) -> GuildConfig:
    result = await session.execute(select(GuildConfig).where(GuildConfig.guild_id == guild_id))
    config = result.scalar_one_or_none()
    if config is None:
        config = GuildConfig(guild_id=guild_id, prefix=DEFAULT_PREFIX)
        session.add(config)
        await session.commit()
        await session.refresh(config)
    return config

async def save_config(guild_id: int, **changes) -> GuildConfig:
    async with SessionLocal() as session:
        config = await get_guild_config(session, guild_id)
        for key, value in changes.items():
            setattr(config, key, value)
        await session.commit()
        await session.refresh(config)
        return config
