
import asyncio
import httpx
import json

async def main():
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("http://localhost:8000/api/v1/timeline?limit=20")
            response.raise_for_status()
            data = response.json()
            print(f"API returned {len(data)} items")
            for item in data:
                print(f"- {item.get('start_time')} : {item.get('activity')} [{item.get('id')}]")
        except Exception as e:
            print(f"Error: {e}")
            if hasattr(e, 'response'):
                print(f"Response: {e.response.text}")

if __name__ == "__main__":
    asyncio.run(main())
