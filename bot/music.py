from __future__ import annotations

import re
import discord
import wavelink
from discord import app_commands

PLATFORM_PATTERNS = {
    "Spotify": re.compile(r"https?://open\\.spotify\\.com/", re.I),
    "Apple Music": re.compile(r"https?://music\\.apple\\.com/", re.I),
    "Deezer": re.compile(r"https?://(?:www\\.)?deezer\\.com/", re.I),
    "TIDAL": re.compile(r"https?://(?:www\\.)?tidal\\.com/", re.I),
}
TEXT_COMMANDS = {"play", "p", "search", "skip", "next", "pause", "resume", "stop", "queue", "q", "volume", "vol", "loop", "shuffle", "clear", "nowplaying", "np", "leave", "disconnect", "join", "help", "musichelp"}

def platform_name(query: str) -> str | None:
    for name, pattern in PLATFORM_PATTERNS.items():
        if pattern.search(query):
            return name
    return None

class Music:
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.loop_modes: dict[int, str] = {}
        self.autoplay: dict[int, bool] = {}

    def player(self, guild: discord.Guild | None) -> wavelink.Player | None:
        if guild is None:
            return None
        voice = guild.voice_client
        return voice if isinstance(voice, wavelink.Player) else None

    async def connect_member(self, guild: discord.Guild, member: discord.Member) -> wavelink.Player:
        if member.voice is None or member.voice.channel is None:
            raise ValueError("Join a voice channel first.")
        player = self.player(guild)
        if player is None:
            player = await member.voice.channel.connect(cls=wavelink.Player)
        elif player.channel != member.voice.channel:
            raise ValueError("Join my current voice channel to control playback.")
        return player

    async def ensure_player(self, interaction: discord.Interaction) -> wavelink.Player:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            raise app_commands.AppCommandError("This command only works in a server.")
        try:
            return await self.connect_member(interaction.guild, interaction.user)
        except ValueError as exc:
            raise app_commands.AppCommandError(str(exc)) from exc

    async def advance(self, player: wavelink.Player) -> None:
        guild_id = player.guild.id if player.guild else 0
        mode = self.loop_modes.get(guild_id, "off")
        previous = player.current
        if mode == "track" and previous is not None:
            await player.play(previous)
            return
        if mode == "queue" and previous is not None:
            await player.queue.put_wait(previous)
        if player.queue:
            await player.play(await player.queue.get_wait())

    async def enqueue(self, guild: discord.Guild, member: discord.Member, query: str) -> str:
        if not query.strip():
            return "Give me a song name or authorized playable URL. Example: play faded"
        platform = platform_name(query)
        if platform:
            return f"This is a {platform} link. Protected audio is not extracted; use an authorized playable source."
        player = await self.connect_member(guild, member)
        tracks = await wavelink.Playable.search(query)
        if not tracks:
            return "No playable results from configured audio sources."
        track = tracks[0]
        await player.queue.put_wait(track)
        if not player.playing:
            await player.play(await player.queue.get_wait())
            return f"▶️ Now playing: {track.title}"
        return f"➕ Added to queue: {track.title}"

    async def play_query(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer()
        try:
            if interaction.guild is None or not isinstance(interaction.user, discord.Member):
                raise ValueError("This command only works in a server.")
            await interaction.followup.send(await self.enqueue(interaction.guild, interaction.user, query))
        except (ValueError, wavelink.WavelinkException) as exc:
            await interaction.followup.send(str(exc), ephemeral=True)

    async def handle_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None or not message.content:
            return
        parts = message.content.strip().split(maxsplit=1)
        command = parts[0].lower()
        if command not in TEXT_COMMANDS:
            return
        arg = parts[1].strip() if len(parts) > 1 else ""
        guild = message.guild
        player = self.player(guild)
        try:
            if command in {"play", "p", "search"}:
                if isinstance(message.author, discord.Member):
                    await message.reply(await self.enqueue(guild, message.author, arg), mention_author=False)
            elif command in {"help", "musichelp"}:
                await message.reply("ZYVORA MUSIC commands: play <song>, search <song>, skip, pause, resume, queue, nowplaying, volume <0-100>, loop <off|track|queue>, shuffle, clear, stop, join, leave.", mention_author=False)
            elif command == "join":
                if isinstance(message.author, discord.Member):
                    await self.connect_member(guild, message.author)
                    await message.reply("🔊 Joined your voice channel.", mention_author=False)
            elif command in {"skip", "next"}:
                if not player or not player.current:
                    return await message.reply("Nothing is playing.", mention_author=False)
                await player.skip()
                await message.reply("⏭️ Skipped.", mention_author=False)
            elif command in {"pause", "resume"}:
                if not player:
                    return await message.reply("No active player.", mention_author=False)
                await player.pause(command == "pause")
                await message.reply("⏸️ Paused." if command == "pause" else "▶️ Resumed.", mention_author=False)
            elif command in {"stop", "clear"}:
                if not player:
                    return await message.reply("No active player.", mention_author=False)
                player.queue.clear()
                if command == "stop":
                    await player.stop()
                await message.reply("⏹️ Stopped and queue cleared." if command == "stop" else "🧹 Upcoming queue cleared.", mention_author=False)
            elif command in {"queue", "q"}:
                if not player:
                    return await message.reply("Queue is empty.", mention_author=False)
                upcoming = list(player.queue)[:10]
                current = f"🎶 Now: {player.current.title}\n" if player.current else ""
                lines = [f"{i + 1}. {track.title}" for i, track in enumerate(upcoming)]
                await message.reply(current + ("\n".join(lines) or "No upcoming tracks."), mention_author=False)
            elif command in {"volume", "vol"}:
                if not player:
                    return await message.reply("No active player.", mention_author=False)
                try:
                    value = int(arg)
                    if not 0 <= value <= 100:
                        raise ValueError
                except ValueError:
                    return await message.reply("Usage: volume 50 (0–100).", mention_author=False)
                await player.set_volume(value)
                await message.reply(f"🔊 Volume set to {value}%.", mention_author=False)
            elif command == "loop":
                if arg.lower() not in {"off", "track", "queue"}:
                    return await message.reply("Usage: loop off, loop track, or loop queue.", mention_author=False)
                self.loop_modes[guild.id] = arg.lower()
                await message.reply(f"🔁 Loop mode: {arg.lower()}", mention_author=False)
            elif command == "shuffle":
                if not player or not player.queue:
                    return await message.reply("No upcoming tracks to shuffle.", mention_author=False)
                player.queue.shuffle()
                await message.reply("🔀 Queue shuffled.", mention_author=False)
            elif command in {"nowplaying", "np"}:
                if not player or not player.current:
                    return await message.reply("Nothing is playing.", mention_author=False)
                await message.reply(f"🎶 Now playing: {player.current.title}", mention_author=False)
            elif command in {"leave", "disconnect"}:
                if not player:
                    return await message.reply("I am not in a voice channel.", mention_author=False)
                player.queue.clear()
                await player.disconnect()
                await message.reply("👋 Disconnected.", mention_author=False)
        except (ValueError, wavelink.WavelinkException, discord.HTTPException) as exc:
            await message.reply(f"⚠️ {exc}", mention_author=False)

    async def register(self, tree: app_commands.CommandTree) -> None:
        @tree.command(name="play", description="Play a permitted track or queue it")
        @app_commands.describe(query="Song name or authorized playable URL")
        async def play(interaction: discord.Interaction, query: str):
            await self.play_query(interaction, query)

        @tree.command(name="search", description="Search configured audio sources")
        async def search(interaction: discord.Interaction, query: str):
            await self.play_query(interaction, query)

        @tree.command(name="skip", description="Skip the current track")
        async def skip(interaction: discord.Interaction):
            player = self.player(interaction.guild)
            if not player or not player.current:
                return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            await player.skip()
            await interaction.response.send_message("⏭️ Skipped.")

        @tree.command(name="pause", description="Pause playback")
        async def pause(interaction: discord.Interaction):
            player = self.player(interaction.guild)
            if not player:
                return await interaction.response.send_message("No active player.", ephemeral=True)
            await player.pause(True)
            await interaction.response.send_message("⏸️ Paused.")

        @tree.command(name="resume", description="Resume playback")
        async def resume(interaction: discord.Interaction):
            player = self.player(interaction.guild)
            if not player:
                return await interaction.response.send_message("No active player.", ephemeral=True)
            await player.pause(False)
            await interaction.response.send_message("▶️ Resumed.")

        @tree.command(name="stop", description="Stop and clear the queue")
        async def stop(interaction: discord.Interaction):
            player = self.player(interaction.guild)
            if not player:
                return await interaction.response.send_message("No active player.", ephemeral=True)
            player.queue.clear()
            await player.stop()
            await interaction.response.send_message("⏹️ Stopped and queue cleared.")

        @tree.command(name="queue", description="Show current and upcoming tracks")
        async def queue(interaction: discord.Interaction):
            player = self.player(interaction.guild)
            if not player:
                return await interaction.response.send_message("Queue is empty.", ephemeral=True)
            upcoming = list(player.queue)[:10]
            current = f"Now: {player.current.title}\n" if player.current else ""
            lines = [f"{i + 1}. {track.title}" for i, track in enumerate(upcoming)]
            await interaction.response.send_message(current + ("\n".join(lines) or "No upcoming tracks."))

        @tree.command(name="volume", description="Set player volume (0-100)")
        async def volume(interaction: discord.Interaction, value: app_commands.Range[int, 0, 100]):
            player = self.player(interaction.guild)
            if not player:
                return await interaction.response.send_message("No active player.", ephemeral=True)
            await player.set_volume(value)
            await interaction.response.send_message(f"🔊 Volume set to {value}%.")

        @tree.command(name="loop", description="Set loop mode")
        @app_commands.choices(mode=[
            app_commands.Choice(name="Off", value="off"),
            app_commands.Choice(name="Track", value="track"),
            app_commands.Choice(name="Queue", value="queue"),
        ])
        async def loop(interaction: discord.Interaction, mode: app_commands.Choice[str]):
            if interaction.guild:
                self.loop_modes[interaction.guild.id] = mode.value
            await interaction.response.send_message(f"🔁 Loop mode: {mode.value}")

        @tree.command(name="nowplaying", description="Show the current track")
        async def nowplaying(interaction: discord.Interaction):
            player = self.player(interaction.guild)
            if not player or not player.current:
                return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            await interaction.response.send_message(f"🎶 {player.current.title}")

        @tree.command(name="leave", description="Disconnect from voice")
        async def leave(interaction: discord.Interaction):
            player = self.player(interaction.guild)
            if not player:
                return await interaction.response.send_message("I am not in a voice channel.", ephemeral=True)
            player.queue.clear()
            await player.disconnect()
            await interaction.response.send_message("👋 Disconnected.")

        @tree.command(name="autoplay", description="Toggle autoplay preference")
        async def autoplay(interaction: discord.Interaction):
            if not interaction.guild:
                return await interaction.response.send_message("Server only.", ephemeral=True)
            guild_id = interaction.guild.id
            self.autoplay[guild_id] = not self.autoplay.get(guild_id, False)
            await interaction.response.send_message(f"Autoplay preference: {'ON' if self.autoplay[guild_id] else 'OFF'} (recommendation engine not enabled).")
