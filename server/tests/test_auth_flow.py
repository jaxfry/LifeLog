import uuid

import pytest
from sqlmodel import select

from app.core.security import hash_password
from app.models.auth import RefreshToken, User


@pytest.mark.asyncio
@pytest.mark.integration
async def test_login_issues_refresh_token(async_client, session):
    user = User(
        id=uuid.uuid4(),
        username="persistent-user",
        hashed_password=hash_password("secret123"),
        is_active=True,
    )
    session.add(user)
    await session.commit()

    response = await async_client.post(
        "/api/v1/token",
        data={"username": "persistent-user", "password": "secret123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"

    statement = select(RefreshToken)
    records = (await session.execute(statement)).scalars().all()
    assert len(records) == 1
    assert records[0].user_id == user.id
    assert not records[0].revoked
    assert records[0].token_hash != body["refresh_token"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_refresh_rotates_token_and_works_after_access_expiry(async_client, session):
    user = User(
        id=uuid.uuid4(),
        username="rotating-user",
        hashed_password=hash_password("secret123"),
        is_active=True,
    )
    session.add(user)
    await session.commit()

    login = await async_client.post(
        "/api/v1/token",
        data={"username": "rotating-user", "password": "secret123"},
    )
    first_refresh = login.json()["refresh_token"]

    response = await async_client.post(
        "/api/v1/token/refresh",
        json={"refresh_token": first_refresh},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"] != first_refresh

    me = await async_client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["username"] == "rotating-user"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_reused_refresh_token_is_rejected_after_rotation(async_client, session):
    user = User(
        id=uuid.uuid4(),
        username="replay-user",
        hashed_password=hash_password("secret123"),
        is_active=True,
    )
    session.add(user)
    await session.commit()

    login = await async_client.post(
        "/api/v1/token",
        data={"username": "replay-user", "password": "secret123"},
    )
    first_refresh = login.json()["refresh_token"]

    first = await async_client.post(
        "/api/v1/token/refresh",
        json={"refresh_token": first_refresh},
    )
    assert first.status_code == 200

    replay = await async_client.post(
        "/api/v1/token/refresh",
        json={"refresh_token": first_refresh},
    )
    assert replay.status_code == 401


@pytest.mark.asyncio
@pytest.mark.integration
async def test_refresh_rejects_garbage_token(async_client, session):
    response = await async_client.post(
        "/api/v1/token/refresh",
        json={"refresh_token": "not-a-real-token"},
    )
    assert response.status_code == 401
