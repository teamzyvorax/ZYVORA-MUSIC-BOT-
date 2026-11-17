from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

import discord
from discord import app_commands


class UserManagement:
    """Member utilities, role tools, persistent warnings and activity ranking."""

    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.db = sqlite3.connect(os.getenv("USERS_DB", "users.sqlite3"))
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS activity (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                messages INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )"""
        )
        self.db.commit()

    def close(self):
        self.db.close()

    def add_warning(self, guild_id: int, user_id: int, moderator_id: int, reason: str) -> int:
        cursor = self.db.execute(
            "INSERT INTO warnings(guild_id,user_id,moderator_id,reason,created_at) VALUES(?,?,?,?,?)",
            (guild_id, user_id, moderator_id, reason[:1000], datetime.now(timezone.utc).isoformat()),
        )
        self.db.commit()
        return int(cursor.lastrowid)

    def get_warnings(self, guild_id: int, user_id: int):
        return self.db.execute(
            "SELECT id,moderator_id,reason,created_at FROM warnings WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 20",
            (guild_id, user_id),
        ).fetchall()

    def clear_warnings(self, guild_id: int, user_id: int) -> int:
        cursor = self.db.execute(
            "DELETE FROM warnings WHERE guild_id=? AND user_id=?",
            (guild_id, user_id),
        )
        self.db.commit()
        return cursor.rowcount

    def track_message(self, message: discord.Message):
        if message.guild and not message.author.bot:
            self.db.execute(
                "INSERT INTO activity(guild_id,user_id,messages) VALUES(?,?,1) "
                "ON CONFLICT(guild_id,user_id) DO UPDATE SET messages=messages+1",
                (message.guild.id, message.author.id),
            )
            self.db.commit()

    async def register(self, tree: app_commands.CommandTree):
        @tree.command(name="userinfo", description="View a member's profile and server details")
        async def userinfo(interaction: discord.Interaction, member: discord.Member | None = None):
            target = member or interaction.user
            if not isinstance(target, discord.Member):
                return await interaction.response.send_message("This command must be used in a server.", ephemeral=True)
            embed = discord.Embed(title=f"{target.display_name}", color=target.color or discord.Color.blurple())
            embed.set_thumbnail(url=target.display_avatar.url)
            embed.add_field(name="Username", value=str(target), inline=True)
            embed.add_field(name="User ID", value=str(target.id), inline=True)
            embed.add_field(name="Bot", value="Yes" if target.bot else "No", inline=True)
            embed.add_field(name="Account created", value=discord.utils.format_dt(target.created_at, style="D"), inline=True)
            embed.add_field(name="Joined server", value=discord.utils.format_dt(target.joined_at, style="D") if target.joined_at else "Unknown", inline=True)
            embed.add_field(name="Top role", value=target.top_role.mention, inline=True)
            embed.add_field(name="Roles", value=str(max(0, len(target.roles) - 1)), inline=True)
            await interaction.response.send_message(embed=embed)

        @tree.command(name="avatar", description="Show a member's profile picture")
        async def avatar(interaction: discord.Interaction, member: discord.Member | None = None):
            target = member or interaction.user
            embed = discord.Embed(title=f"{target.display_name}'s avatar", color=discord.Color.blurple())
            embed.set_image(url=target.display_avatar.url)
            embed.add_field(name="Links", value=f"[PNG]({target.display_avatar.with_format('png').url}) · [WEBP]({target.display_avatar.with_format('webp').url})")
            await interaction.response.send_message(embed=embed)

        @tree.command(name="serverinfo", description="Show information about this server")
        async def serverinfo(interaction: discord.Interaction):
            guild = interaction.guild
            if guild is None:
                return await interaction.response.send_message("Use this command in a server.", ephemeral=True)
            embed = discord.Embed(title=guild.name, color=discord.Color.blurple())
            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)
            embed.add_field(name="Server ID", value=str(guild.id), inline=True)
            embed.add_field(name="Owner", value=f"<@{guild.owner_id}>", inline=True)
            embed.add_field(name="Members", value=str(guild.member_count or "Unknown"), inline=True)
            embed.add_field(name="Text channels", value=str(len(guild.text_channels)), inline=True)
            embed.add_field(name="Voice channels", value=str(len(guild.voice_channels)), inline=True)
            embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
            embed.add_field(name="Created", value=discord.utils.format_dt(guild.created_at, style="D"), inline=True)
            await interaction.response.send_message(embed=embed)

        @tree.command(name="membercount", description="Show the server member count")
        async def membercount(interaction: discord.Interaction):
            if interaction.guild is None:
                return await interaction.response.send_message("Use this command in a server.", ephemeral=True)
            await interaction.response.send_message(f"👥 **{interaction.guild.name}** has **{interaction.guild.member_count or 'an unknown number of'}** members.")

        @tree.command(name="nickname", description="Change a member's server nickname")
        @app_commands.default_permissions(manage_nicknames=True)
        @app_commands.checks.has_permissions(manage_nicknames=True)
        async def nickname(interaction: discord.Interaction, member: discord.Member, name: app_commands.Range[str, 1, 32]):
            if member.id == interaction.guild.owner_id or member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
                return await interaction.response.send_message("You cannot change the nickname of a member with an equal or higher role.", ephemeral=True)
            if interaction.guild.me and member.top_role >= interaction.guild.me.top_role:
                return await interaction.response.send_message("The bot's role must be above the target member.", ephemeral=True)
            try:
                await member.edit(nick=name, reason=f"Nickname changed by {interaction.user}")
                await interaction.response.send_message(f"✅ Updated {member.mention}'s nickname.", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("I need Manage Nicknames and a higher role than the target.", ephemeral=True)

        role_group = app_commands.Group(name="role", description="Add or remove a server role from a member")

        @role_group.command(name="add", description="Give a role to a member")
        @app_commands.default_permissions(manage_roles=True)
        @app_commands.checks.has_permissions(manage_roles=True)
        async def role_add(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
            if role.is_default() or role.managed or role >= interaction.guild.me.top_role:
                return await interaction.response.send_message("I cannot assign @everyone, integration-managed roles, or roles at/above my highest role.", ephemeral=True)
            if interaction.user.id != interaction.guild.owner_id and role >= interaction.user.top_role:
                return await interaction.response.send_message("You can only assign roles below your highest role.", ephemeral=True)
            try:
                await member.add_roles(role, reason=f"Role added by {interaction.user}")
                await interaction.response.send_message(f"✅ Added {role.mention} to {member.mention}.", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("I need Manage Roles and the bot's highest role must be above that role.", ephemeral=True)

        @role_group.command(name="remove", description="Remove a role from a member")
        @app_commands.default_permissions(manage_roles=True)
        @app_commands.checks.has_permissions(manage_roles=True)
        async def role_remove(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
            if role.is_default() or role.managed or role >= interaction.guild.me.top_role:
                return await interaction.response.send_message("I cannot remove @everyone, integration-managed roles, or roles at/above my highest role.", ephemeral=True)
            if interaction.user.id != interaction.guild.owner_id and role >= interaction.user.top_role:
                return await interaction.response.send_message("You can only remove roles below your highest role.", ephemeral=True)
            try:
                await member.remove_roles(role, reason=f"Role removed by {interaction.user}")
                await interaction.response.send_message(f"✅ Removed {role.mention} from {member.mention}.", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("I need Manage Roles and the bot's highest role must be above that role.", ephemeral=True)

        tree.add_command(role_group)

        @tree.command(name="warns", description="View a member's recent moderation warnings")
        @app_commands.default_permissions(moderate_members=True)
        @app_commands.checks.has_permissions(moderate_members=True)
        async def warns(interaction: discord.Interaction, member: discord.Member):
            rows = self.get_warnings(interaction.guild_id, member.id)
            if not rows:
                return await interaction.response.send_message(f"✅ {member.mention} has no recorded warnings.", ephemeral=True)
            lines = []
            for warning_id, moderator_id, reason, created_at in rows:
                stamp = datetime.fromisoformat(created_at).strftime("%Y-%m-%d %H:%M UTC")
                lines.append(f"**#{warning_id}** · {stamp}\nModerator: <@{moderator_id}>\nReason: {discord.utils.escape_markdown(reason)}")
            embed = discord.Embed(title=f"Warnings — {member}", description="\n\n".join(lines)[:4000], color=discord.Color.orange())
            await interaction.response.send_message(embed=embed, ephemeral=True)

        @tree.command(name="warnings_clear", description="Clear all stored warnings for a member")
        @app_commands.default_permissions(moderate_members=True)
        @app_commands.checks.has_permissions(moderate_members=True)
        async def warnings_clear(interaction: discord.Interaction, member: discord.Member):
            count = self.clear_warnings(interaction.guild_id, member.id)
            await interaction.response.send_message(f"🧹 Cleared **{count}** stored warning(s) for {member.mention}.", ephemeral=True)

        @tree.command(name="leaderboard", description="Show the most active members by message count")
        async def leaderboard(interaction: discord.Interaction):
            rows = self.db.execute(
                "SELECT user_id,messages FROM activity WHERE guild_id=? ORDER BY messages DESC LIMIT 10",
                (interaction.guild_id,),
            ).fetchall()
            if not rows:
                return await interaction.response.send_message("No activity has been recorded yet. New messages will count from now on.", ephemeral=True)
            lines = []
            for index, (user_id, count) in enumerate(rows, start=1):
                lines.append(f"**{index}.** <@{user_id}> — **{count}** messages")
            embed = discord.Embed(title="🏆 Server Activity Leaderboard", description="\n".join(lines), color=discord.Color.gold())
            embed.set_footer(text="Counts begin when this feature is enabled; bots are excluded.")
            await interaction.response.send_message(embed=embed)
