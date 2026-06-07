import httpx
import asyncio
import json

async def test():
    # Login as user to get token
    async with httpx.AsyncClient(base_url="http://api.serverdeck.online/api") as client:
        # First, we need a valid token. If we don't have one, we can't do it easily unless we know the credentials.
        # Alternatively, we can check the db directly. But the user has the browser running.
        # Let's just make a request without token and see what error it returns.
        res = await client.post("/servers/8b8b22f4-0216-47e4-98d5-b0d7315b7e53/alert-rules", json={
            "name": "High CPU",
            "metric": "cpu",
            "threshold": 1.0,
            "service_name": None,
            "ssl_domain": None
        })
        print(f"Status: {res.status_code}")
        print(f"Body: {res.text}")

asyncio.run(test())
