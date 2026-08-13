import asyncio
import os
import sys

# Add the parent directory to sys.path so we can import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from sqlmodel import select

from app.core.database import async_session_factory
from app.core.security import get_password_hash
from app.models.auth import User


async def create_superuser():
    async with async_session_factory() as session:
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
