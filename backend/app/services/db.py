"""
数据库会话与操作。SQLite 用于本地开发（零配置），
切换到 PostgreSQL 只需改 DATABASE_URL 环境变量。
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.config import settings
from app.models.profile import UserProfile, Base

engine = create_async_engine(settings.database_url, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """创建所有表（启动时调用）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def save_or_update_profile(
    user_id: str,
    basic_fields: dict,
    tags: dict,
    bio: str,
) -> str:
    """保存或更新用户资料，返回 user_id"""
    async with async_session() as session:
        stmt = select(UserProfile).where(UserProfile.user_id == user_id)
        result = await session.execute(stmt)
        profile = result.scalar_one_or_none()

        field_map = {
            "avatar_url": "avatar_url",
            "nickname": "nickname",
            "age": "age",
            "occupation": "occupation",
            "region": "region",
            "languages": "languages",
            "demand_types": "demand_types",
        }

        if profile:
            for src_key, db_col in field_map.items():
                if src_key in basic_fields:
                    setattr(profile, db_col, basic_fields[src_key])
            profile.tags = tags
            profile.bio = bio
        else:
            profile = UserProfile(
                user_id=user_id,
                avatar_url=basic_fields.get("avatar_url"),
                nickname=basic_fields.get("nickname"),
                age=basic_fields.get("age"),
                occupation=basic_fields.get("occupation"),
                region=basic_fields.get("region"),
                languages=basic_fields.get("languages", []),
                demand_types=basic_fields.get("demand_types", []),
                tags=tags,
                bio=bio,
            )
            session.add(profile)

        await session.commit()
        return user_id
