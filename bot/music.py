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

    async def ensure_player(self, interaction: discord.Interaction) -> wavelink.Player:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            raise app_commands.AppCommandError("This command only works in a server.")
        member = interaction.user
        if member.voice is None or member.voice.channel is None:
            raise app_commands.AppCommandError("Join a voice channel first.")
        player = self.player(interaction.guild)
        if player is None:
            player = await member.voice.channel.connect(cls=wavelink.Player)
        elif player.channel != member.voice.channel:
            raise app_commands.AppCommandError("Join my current voice channel to control playback.")
        return player

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

    async def play_query(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer()
        platform = platform_name(query)
        if platform:
            await interaction.followup.send(
                f"This is a {platform} link. Protected audio is not extracted. "
                "Use an authorized playable source or a provider integration that grants playback rights.",
                ephemeral=True,
            )
            return
        try:
            player = await self.ensure_player(interaction)
            tracks = await wavelink.Playable.search(query)
            if not tracks:
                await interaction.followup.send("No playable results from configured sources.", ephemeral=True)
                return
            track = tracks[0]
            await player.queue.put_wait(track)
            if not player.playing:
                await player.play(await player.queue.get_wait())
                await interaction.followup.send(f"▶️ Now playing **{track.title}**")
            else:
                await interaction.followup.send(f"➕ Added **{track.title}** to the queue.")
        except (app_commands.AppCommandError, wavelink.WavelinkException) as exc:
            await interaction.followup.send(str(exc), ephemeral=True)

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
            lines = [f"{i + 1}. {track.title}" for i, track in enumerate(upcoming)]
            current = f"**Now:** {player.current.title}\\n" if player.current else ""
            await interaction.response.send_message(current + ("\\n".join(lines) or "No upcoming tracks."))

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
            await interaction.response.send_message(f"🔁 Loop mode: **{mode.value}**")

        @tree.command(name="nowplaying", description="Show the current track")
        async def nowplaying(interaction: discord.Interaction):
            player = self.player(interaction.guild)
            if not player or not player.current:
                return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            await interaction.response.send_message(f"🎶 **{player.current.title}**")

        @tree.command(name="leave", description="Disconnect from voice")
        async def leave(interaction: discord.Interaction):
            player = self.player(interaction.guild)
            if not player:
                return await interaction.response.send_message("I am not in a voice channel.", ephemeral=True)
            await player.disconnect()
            await interaction.response.send_message("👋 Disconnected.")

        @tree.command(name="autoplay", description="Toggle autoplay preference")
        async def autoplay(interaction: discord.Interaction):
            if not interaction.guild:
                return await interaction.response.send_message("Server only.", ephemeral=True)
            guild_id = interaction.guild.id
            self.autoplay[guild_id] = not self.autoplay.get(guild_id, False)
            await interaction.response.send_message(
                f"Autoplay preference: **{'ON' if self.autoplay[guild_id] else 'OFF'}** "
                "(automatic recommendations are not implemented yet)."
            )
