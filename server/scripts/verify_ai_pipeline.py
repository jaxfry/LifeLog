import asyncio
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

# Add server to path
sys.path.append(str(Path(__file__).parent.parent))

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.database import engine
from app.main import app
from app.models.files import FileAttachment
from app.workers.files import task_process_file_batch

# Mock ARQ pool
app.state.arq_pool = AsyncMock()
app.state.arq_pool.enqueue_job = AsyncMock(return_value=None)

async def main():
    print("1. Creating dummy file...")
    dummy_content = (
        b"This is a test file for LifeLog AI analysis. It contains "
        b"keywords like Python, FastAPI, and Gemini."
    )
    files = {'file': ('test_doc.txt', dummy_content, 'text/plain')}

    print("2. Uploading file...")
    # Use AsyncClient with ASGITransport to run the app in the same loop
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/upload",
            files=files,
            data={"category": "document", "tags": "test,ai"},
            headers={"Host": "localhost"},
        )

    if response.status_code != 201:
        print(f"Upload failed: {response.text}")
        return

    file_data = response.json()
    file_id = uuid.UUID(file_data["id"])
    print(f"Upload successful. File ID: {file_id}")

    print("3. Running worker task manually...")
    ctx = {}
    await task_process_file_batch(ctx)

    print("4. Inspecting Database...")
    await inspect_db(file_id)


async def inspect_db(file_id):
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        file = await session.get(FileAttachment, file_id)
        if not file:
            print("File not found in DB!")
            return

        print(f"\n--- File Analysis Results for {file.filename} ---")
        print(f"Processed: {file.is_processed}")

        print("\nAI Metadata:")
        import json

        print(json.dumps(file.ai_metadata, indent=2))

        if file.is_processed and file.ai_metadata:
            print("\nSUCCESS: Pipeline verified!")
        else:
            print("\nFAILURE: Pipeline did not complete successfully.")


if __name__ == "__main__":
    asyncio.run(main())
