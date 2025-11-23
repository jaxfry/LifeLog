import asyncio
import os
import sys

# Add the parent directory to sys.path so we can import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from app.core.db import get_session
from app.models.config import User
from app.core.security import get_password_hash
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://lifelog:lifelogpassword@localhost:5432/lifelog_db")

async def create_superuser():
    engine = create_async_engine(DATABASE_URL, echo=True, future=True)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        username = "admin"
        password = "adminpassword"
        
        statement = select(User).where(User.username == username)
        result = await session.execute(statement)
        user = result.scalars().first()
        
        if user:
            print(f"User {username} already exists")
        else:
            user = User(
                username=username,
                hashed_password=get_password_hash(password),
                is_superuser=True,
                is_active=True
            )
            session.add(user)
            await session.commit()
            print(f"Superuser {username} created successfully")

if __name__ == "__main__":
    asyncio.run(create_superuser())
