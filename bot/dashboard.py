import asyncio
import os

from fastapi import FastAPI
import uvicorn

app = FastAPI(title="ZYVORA MUSIC API", version="0.1.0")
_bot = None


@app.get("/health")
async def health():
    ready = bool(_bot and _bot.is_ready())
    return {
        "ok": True,
        "service": "ZYVORA MUSIC BOT",
        "discord_ready": ready,
        "guild_count": len(_bot.guilds) if ready else 0,
    }


async def start_dashboard(bot):
    global _bot
    _bot = bot
    host = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.getenv("DASHBOARD_PORT", "8080"))
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    asyncio.create_task(server.serve())
