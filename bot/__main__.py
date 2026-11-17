import asyncio
import os
import discord
import wavelink
from dotenv import load_dotenv
from .dashboard import start_dashboard
from .music import Music
from .moderation import Moderation
from .community import Community

load_dotenv()

class ZyvoraBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.voice_states = True
        # Required for no-prefix text commands; also enable in Discord Developer Portal.
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = discord.app_commands.CommandTree(self)
        self.music = Music(self)
        self.moderation = Moderation(self)
        self.community = Community(self)

    async def setup_hook(self):
        host = os.getenv("LAVALINK_HOST", "localhost")
        port = int(os.getenv("LAVALINK_PORT", "2333"))
        password = os.getenv("LAVALINK_PASSWORD")
        if not password:
            raise RuntimeError("LAVALINK_PASSWORD is missing.")
        node = wavelink.Node(uri=f"http://{host}:{port}", password=password)
        await wavelink.Pool.connect(client=self, nodes=[node])
        await self.music.register(self.tree)
        await self.moderation.register(self.tree)
        await self.community.register(self.tree)
        await self.tree.sync()

    async def on_message(self, message: discord.Message):
        await self.music.handle_message(message)

    async def on_wavelink_track_end(self, payload):
        player = payload.player
        if not player:
            return
        try:
            await self.music.advance(player)
        except Exception as exc:
            print(f"Queue advance failed: {exc}")

    async def on_ready(self):
        await self.community.on_ready()
        print(f"ZYVORA MUSIC online as {self.user} | servers={len(self.guilds)}")

async def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is missing. Copy .env.example to .env.")
    bot = ZyvoraBot()
    await start_dashboard(bot)
    async with bot:
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
