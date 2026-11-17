from __future__ import annotations

import asyncio
import os
import random
import sqlite3
from datetime import timedelta

import aiohttp
import discord
from discord import app_commands
from discord.ext import tasks


class Community:
    """Rules, announcements, giveaways and YouTube upload notifications."""

    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.db = sqlite3.connect(os.getenv("COMMUNITY_DB", "community.sqlite3"))
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS youtube_subscriptions (
                guild_id INTEGER NOT NULL,
                channel_id TEXT NOT NULL,
                channel_name TEXT NOT NULL,
                announce_channel_id INTEGER NOT NULL,
                last_video_id TEXT,
                PRIMARY KEY (guild_id, channel_id)
            )"""
        )
        self.db.commit()
        self.youtube_key = os.getenv("YOUTUBE_API_KEY", "").strip()
        self.giveaway_tasks: set[asyncio.Task] = set()

    async def close(self):
        for task in tuple(self.giveaway_tasks):
            task.cancel()
        self.db.close()

    async def on_ready(self):
        if self.youtube_key and not self.youtube_poll.is_running():
            self.youtube_poll.start()

    @tasks.loop(minutes=5)
    async def youtube_poll(self):
        rows = self.db.execute(
            "SELECT guild_id, channel_id, channel_name, announce_channel_id, last_video_id FROM youtube_subscriptions"
        ).fetchall()
        if not rows:
            return
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for guild_id, channel_id, channel_name, announce_id, last_id in rows:
                try:
                    params = {
                        "key": self.youtube_key,
                        "channelId": channel_id,
                        "part": "snippet",
                        "order": "date",
                        "type": "video",
                        "maxResults": "1",
                    }
                    async with session.get("https://www.googleapis.com/youtube/v3/search", params=params) as response:
                        if response.status != 200:
                            print(f"YouTube API returned HTTP {response.status} for {channel_id}")
                            continue
                        payload = await response.json()
                    items = payload.get("items", [])
                    if not items:
                        continue
                    item = items[0]
                    video_id = item.get("id", {}).get("videoId")
                    snippet = item.get("snippet", {})
                    if not video_id or video_id == last_id:
                        continue
                    # Store before sending so a temporary Discord failure does not spam retries.
                    self.db.execute(
                        "UPDATE youtube_subscriptions SET last_video_id=? WHERE guild_id=? AND channel_id=?",
                        (video_id, guild_id, channel_id),
                    )
                    self.db.commit()
                    channel = self.bot.get_channel(announce_id)
                    if not isinstance(channel, discord.TextChannel):
                        continue
                    title = discord.utils.escape_markdown(snippet.get("title", "New video"))
                    url = f"https://www.youtube.com/watch?v={video_id}"
                    embed = discord.Embed(
                        title=title[:256],
                        url=url,
                        description=f"**{discord.utils.escape_markdown(channel_name)}** uploaded a new video.",
                        color=discord.Color.red(),
                    )
                    thumbnails = snippet.get("thumbnails", {})
                    thumb = thumbnails.get("high") or thumbnails.get("medium") or thumbnails.get("default")
                    if thumb and thumb.get("url"):
                        embed.set_thumbnail(url=thumb["url"])
                    await channel.send(content="📺 **New YouTube upload!**", embed=embed)
                except (aiohttp.ClientError, asyncio.TimeoutError, discord.Forbidden) as exc:
                    print(f"YouTube notification error for {channel_id}: {exc}")
                except Exception as exc:
                    print(f"YouTube poll error for {channel_id}: {exc}")

    @youtube_poll.before_loop
    async def before_youtube_poll(self):
        await self.bot.wait_until_ready()

    async def register(self, tree: app_commands.CommandTree):
        @tree.command(name="rules", description="Post the server rules")
        async def rules(interaction: discord.Interaction):
            embed = discord.Embed(
                title=f"{interaction.guild.name if interaction.guild else 'Server'} — Rules & Regulations",
                description=(
                    "Please follow these rules to keep this community safe and welcoming. "
                    "Staff may remove content or take action when needed."
                ),
                color=discord.Color.blurple(),
            )
            rules_list = [
                ("1. Respect everyone", "No harassment, hate speech, bullying, threats or discrimination."),
                ("2. Keep it appropriate", "No NSFW, illegal, shocking or otherwise prohibited content."),
                ("3. No spam or raids", "Avoid floods, repeated messages, mass mentions and disruptive behaviour."),
                ("4. Use the right channels", "Keep conversations, links, media and support in their relevant channels."),
                ("5. No scams or malicious links", "No phishing, malware, impersonation, fake giveaways or suspicious promotions."),
                ("6. Respect privacy", "Do not share anyone's personal information, private messages or account details without consent."),
                ("7. Follow Discord rules", "Follow Discord's Terms of Service and Community Guidelines."),
                ("8. Listen to moderators", "Do not evade moderation. Appeal calmly through the server's approved process."),
            ]
            for title, description in rules_list:
                embed.add_field(name=title, value=description, inline=False)
            embed.set_footer(text="By participating, you agree to follow these rules. Rules may be updated by staff.")
            await interaction.response.send_message(embed=embed)

        @tree.command(name="announce", description="Post a server announcement")
        @app_commands.default_permissions(manage_guild=True)
        @app_commands.checks.has_permissions(manage_guild=True)
        @app_commands.describe(channel="Where to post", title="Announcement title", message="Announcement text")
        async def announce(interaction: discord.Interaction, channel: discord.TextChannel, title: str, message: str):
            if len(message) > 4000:
                return await interaction.response.send_message("Announcement text must be 4000 characters or fewer.", ephemeral=True)
            embed = discord.Embed(title=title[:256], description=message, color=discord.Color.blurple())
            embed.set_footer(text=f"Announcement by {interaction.user.display_name}")
            try:
                await channel.send(embed=embed)
                await interaction.response.send_message(f"📢 Announcement posted in {channel.mention}.", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("I need permission to view and send messages in that channel.", ephemeral=True)

        @tree.command(name="giveaway", description="Start a timed giveaway")
        @app_commands.default_permissions(manage_guild=True)
        @app_commands.checks.has_permissions(manage_guild=True)
        @app_commands.describe(prize="What members can win", duration_minutes="Giveaway duration (1-10080 minutes)", winners="Number of winners (1-10)")
        async def giveaway(
            interaction: discord.Interaction,
            prize: str,
            duration_minutes: app_commands.Range[int, 1, 10080],
            winners: app_commands.Range[int, 1, 10] = 1,
        ):
            if len(prize) > 200:
                return await interaction.response.send_message("Prize must be 200 characters or fewer.", ephemeral=True)
            end_at = discord.utils.utcnow() + timedelta(minutes=duration_minutes)
            embed = discord.Embed(
                title="🎉 GIVEAWAY",
                description=f"**Prize:** {discord.utils.escape_markdown(prize)}\n**Winners:** {winners}\n**Ends:** <t:{int(end_at.timestamp())}:R>\n\nReact with 🎉 to enter!",
                color=discord.Color.gold(),
            )
            embed.set_footer(text=f"Hosted by {interaction.user}")
            await interaction.response.send_message("Giveaway started.")
            message = await interaction.channel.send(embed=embed)
            await message.add_reaction("🎉")
            task = asyncio.create_task(self.finish_giveaway(message, prize, winners, duration_minutes * 60))
            self.giveaway_tasks.add(task)
            task.add_done_callback(self.giveaway_tasks.discard)

        @tree.command(name="youtube_add", description="Subscribe this server to a YouTube channel's new uploads")
        @app_commands.default_permissions(manage_guild=True)
        @app_commands.checks.has_permissions(manage_guild=True)
        @app_commands.describe(channel_id="YouTube channel ID (starts with UC)", announce_channel="Discord channel for upload alerts")
        async def youtube_add(interaction: discord.Interaction, channel_id: str, announce_channel: discord.TextChannel):
            if not self.youtube_key:
                return await interaction.response.send_message("YouTube alerts are not configured. Add YOUTUBE_API_KEY to the bot environment and restart.", ephemeral=True)
            channel_id = channel_id.strip()
            if not channel_id.startswith("UC") or len(channel_id) < 20:
                return await interaction.response.send_message("Enter the YouTube channel ID (usually starts with UC), not a video URL or handle.", ephemeral=True)
            await interaction.response.defer(ephemeral=True)
            try:
                params = {"key": self.youtube_key, "id": channel_id, "part": "snippet"}
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                    async with session.get("https://www.googleapis.com/youtube/v3/channels", params=params) as response:
                        data = await response.json()
                        if response.status != 200 or not data.get("items"):
                            return await interaction.followup.send("YouTube channel not found or API key/quota issue. Check the channel ID and API key.", ephemeral=True)
                name = data["items"][0]["snippet"]["title"]
                # Seed the latest existing upload so subscribing does not announce an old video.
                search_params = {
                    "key": self.youtube_key,
                    "channelId": channel_id,
                    "part": "snippet",
                    "order": "date",
                    "type": "video",
                    "maxResults": "1",
                }
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                    async with session.get("https://www.googleapis.com/youtube/v3/search", params=search_params) as response:
                        latest_data = await response.json()
                        if response.status != 200:
                            return await interaction.followup.send("YouTube API could not read this channel's uploads. Check API access and quota.", ephemeral=True)
                latest_items = latest_data.get("items", [])
                latest_id = latest_items[0].get("id", {}).get("videoId") if latest_items else None
                self.db.execute(
                    "INSERT INTO youtube_subscriptions(guild_id, channel_id, channel_name, announce_channel_id, last_video_id) VALUES(?,?,?,?,?) "
                    "ON CONFLICT(guild_id, channel_id) DO UPDATE SET channel_name=excluded.channel_name, announce_channel_id=excluded.announce_channel_id, last_video_id=excluded.last_video_id",
                    (interaction.guild_id, channel_id, name, announce_channel.id, latest_id),
                )
                self.db.commit()
                if not self.youtube_poll.is_running():
                    self.youtube_poll.start()
                await interaction.followup.send(f"✅ Alerts enabled for **{discord.utils.escape_markdown(name)}** in {announce_channel.mention}. First check runs within five minutes.", ephemeral=True)
            except (aiohttp.ClientError, asyncio.TimeoutError):
                await interaction.followup.send("Could not reach YouTube right now. Try again later.", ephemeral=True)

        @tree.command(name="youtube_remove", description="Remove a YouTube upload alert")
        @app_commands.default_permissions(manage_guild=True)
        @app_commands.checks.has_permissions(manage_guild=True)
        async def youtube_remove(interaction: discord.Interaction, channel_id: str):
            cursor = self.db.execute("DELETE FROM youtube_subscriptions WHERE guild_id=? AND channel_id=?", (interaction.guild_id, channel_id.strip()))
            self.db.commit()
            await interaction.response.send_message("YouTube alert removed." if cursor.rowcount else "No matching subscription found.", ephemeral=True)

        @tree.command(name="youtube_list", description="List this server's YouTube upload alerts")
        async def youtube_list(interaction: discord.Interaction):
            rows = self.db.execute("SELECT channel_name, channel_id, announce_channel_id FROM youtube_subscriptions WHERE guild_id=?", (interaction.guild_id,)).fetchall()
            if not rows:
                return await interaction.response.send_message("No YouTube channels are being monitored in this server.", ephemeral=True)
            lines = [f"• **{discord.utils.escape_markdown(name)}** — <https://www.youtube.com/channel/{cid}> → <#{announce_id}>" for name, cid, announce_id in rows]
            await interaction.response.send_message("\n".join(lines), ephemeral=True)

    async def finish_giveaway(self, message: discord.Message, prize: str, winner_count: int, delay: int):
        await asyncio.sleep(delay)
        try:
            message = await message.channel.fetch_message(message.id)
            reaction = discord.utils.get(message.reactions, emoji="🎉")
            entrants = []
            if reaction:
                async for user in reaction.users():
                    if not user.bot:
                        entrants.append(user)
            winners = random.sample(entrants, min(winner_count, len(entrants))) if entrants else []
            if winners:
                mentions = ", ".join(user.mention for user in winners)
                await message.reply(f"🎊 Congratulations {mentions}! You won **{discord.utils.escape_markdown(prize)}**.")
            else:
                await message.reply(f"Giveaway ended for **{discord.utils.escape_markdown(prize)}**, but there were no valid entries.")
        except (discord.NotFound, discord.Forbidden):
            pass
