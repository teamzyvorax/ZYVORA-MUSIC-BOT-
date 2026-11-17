from __future__ import annotations

import os
from datetime import timedelta

import discord
from discord import app_commands


class Moderation:
    """Permission-checked server moderation slash commands."""

    def __init__(self, bot: discord.Client, users=None):
        self.bot = bot
        self.users = users
        raw_log_id = os.getenv("MOD_LOG_CHANNEL_ID", "").strip()
        self.log_channel_id = int(raw_log_id) if raw_log_id.isdigit() else None

    async def log(self, guild: discord.Guild, title: str, description: str, moderator: discord.abc.User):
        if not self.log_channel_id:
            return
        channel = guild.get_channel(self.log_channel_id)
        if isinstance(channel, discord.TextChannel):
            embed = discord.Embed(title=title, description=description, color=discord.Color.blurple(), timestamp=discord.utils.utcnow())
            embed.set_footer(text=f"Moderator: {moderator} ({moderator.id})")
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass

    @staticmethod
    def hierarchy_error(interaction: discord.Interaction, target: discord.Member) -> str | None:
        guild = interaction.guild
        actor = interaction.user
        if guild is None or not isinstance(actor, discord.Member):
            return "This command can only be used in a server."
        if target.id == actor.id:
            return "You cannot moderate yourself."
        if target.id == guild.owner_id:
            return "The server owner cannot be moderated by this bot."
        if target.top_role >= actor.top_role and actor.id != guild.owner_id:
            return "That member has an equal or higher role than you."
        bot_member = guild.me
        if bot_member and target.top_role >= bot_member.top_role:
            return "That member's role is equal to or higher than the bot's role."
        return None

    async def register(self, tree: app_commands.CommandTree) -> None:
        @tree.command(name="kick", description="Kick a member from this server")
        @app_commands.default_permissions(kick_members=True)
        @app_commands.checks.has_permissions(kick_members=True)
        @app_commands.describe(member="Member to kick", reason="Reason shown in the audit log")
        async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
            error = self.hierarchy_error(interaction, member)
            if error:
                return await interaction.response.send_message(error, ephemeral=True)
            try:
                await member.kick(reason=f"{reason} | Moderator: {interaction.user}")
                await self.log(interaction.guild, "Member kicked", f"{member.mention} ({member.id})\nReason: {reason}", interaction.user)
                await interaction.response.send_message(f"👢 Kicked **{member}**. Reason: {reason}", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("I need the Kick Members permission and a higher role than the target.", ephemeral=True)

        @tree.command(name="ban", description="Ban a member from this server")
        @app_commands.default_permissions(ban_members=True)
        @app_commands.checks.has_permissions(ban_members=True)
        @app_commands.describe(member="Member to ban", reason="Reason shown in the audit log", delete_message_days="Delete recent message history (0-7 days)")
        async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided", delete_message_days: app_commands.Range[int, 0, 7] = 0):
            error = self.hierarchy_error(interaction, member)
            if error:
                return await interaction.response.send_message(error, ephemeral=True)
            try:
                await member.ban(reason=f"{reason} | Moderator: {interaction.user}", delete_message_seconds=delete_message_days * 86400)
                await self.log(interaction.guild, "Member banned", f"{member} ({member.id})\nReason: {reason}", interaction.user)
                await interaction.response.send_message(f"🔨 Banned **{member}**. Reason: {reason}", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("I need the Ban Members permission and a higher role than the target.", ephemeral=True)

        @tree.command(name="unban", description="Unban a user by Discord ID")
        @app_commands.default_permissions(ban_members=True)
        @app_commands.checks.has_permissions(ban_members=True)
        async def unban(interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
            if not user_id.isdigit():
                return await interaction.response.send_message("Enter a numeric Discord user ID.", ephemeral=True)
            try:
                user = await self.bot.fetch_user(int(user_id))
                await interaction.guild.unban(user, reason=f"{reason} | Moderator: {interaction.user}")
                await self.log(interaction.guild, "User unbanned", f"{user} ({user.id})\nReason: {reason}", interaction.user)
                await interaction.response.send_message(f"✅ Unbanned **{user}**.", ephemeral=True)
            except discord.NotFound:
                await interaction.response.send_message("That user is not currently banned (or the ID is invalid).", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("I need the Ban Members permission.", ephemeral=True)

        @tree.command(name="timeout", description="Temporarily prevent a member from chatting")
        @app_commands.default_permissions(moderate_members=True)
        @app_commands.checks.has_permissions(moderate_members=True)
        @app_commands.describe(member="Member to timeout", minutes="Duration, 1 to 40320 minutes (28 days)", reason="Reason")
        async def timeout(interaction: discord.Interaction, member: discord.Member, minutes: app_commands.Range[int, 1, 40320], reason: str = "No reason provided"):
            error = self.hierarchy_error(interaction, member)
            if error:
                return await interaction.response.send_message(error, ephemeral=True)
            try:
                await member.timeout(timedelta(minutes=minutes), reason=f"{reason} | Moderator: {interaction.user}")
                await self.log(interaction.guild, "Member timed out", f"{member.mention} ({member.id})\nDuration: {minutes} minutes\nReason: {reason}", interaction.user)
                await interaction.response.send_message(f"⏳ Timed out **{member}** for {minutes} minutes.", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("I need the Moderate Members permission and a higher role than the target.", ephemeral=True)

        @tree.command(name="untimeout", description="Remove a member's timeout")
        @app_commands.default_permissions(moderate_members=True)
        @app_commands.checks.has_permissions(moderate_members=True)
        async def untimeout(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
            error = self.hierarchy_error(interaction, member)
            if error:
                return await interaction.response.send_message(error, ephemeral=True)
            try:
                await member.timeout(None, reason=f"{reason} | Moderator: {interaction.user}")
                await self.log(interaction.guild, "Timeout removed", f"{member.mention} ({member.id})\nReason: {reason}", interaction.user)
                await interaction.response.send_message(f"✅ Timeout removed for **{member}**.", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("I need the Moderate Members permission.", ephemeral=True)

        @tree.command(name="purge", description="Delete 1-100 recent messages in this channel")
        @app_commands.default_permissions(manage_messages=True)
        @app_commands.checks.has_permissions(manage_messages=True)
        async def purge(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
            if not isinstance(interaction.channel, discord.TextChannel):
                return await interaction.response.send_message("Use this in a server text channel.", ephemeral=True)
            try:
                await interaction.response.defer(ephemeral=True)
                deleted = await interaction.channel.purge(limit=amount)
                await interaction.followup.send(f"🧹 Deleted {len(deleted)} messages.", ephemeral=True)
                await self.log(interaction.guild, "Messages purged", f"Deleted {len(deleted)} messages in {interaction.channel.mention}.", interaction.user)
            except discord.Forbidden:
                await interaction.followup.send("I need Manage Messages and Read Message History permissions.", ephemeral=True)

        @tree.command(name="slowmode", description="Set channel slowmode in seconds (0-21600)")
        @app_commands.default_permissions(manage_channels=True)
        @app_commands.checks.has_permissions(manage_channels=True)
        async def slowmode(interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 21600]):
            if not isinstance(interaction.channel, discord.TextChannel):
                return await interaction.response.send_message("Use this in a server text channel.", ephemeral=True)
            try:
                await interaction.channel.edit(slowmode_delay=seconds, reason=f"Set by {interaction.user}")
                await interaction.response.send_message(f"🐢 Slowmode set to {seconds} seconds.", ephemeral=True)
                await self.log(interaction.guild, "Slowmode changed", f"{interaction.channel.mention}: {seconds} seconds.", interaction.user)
            except discord.Forbidden:
                await interaction.response.send_message("I need Manage Channels permission.", ephemeral=True)

        async def set_lock(interaction: discord.Interaction, locked: bool):
            if not isinstance(interaction.channel, discord.TextChannel):
                return await interaction.response.send_message("Use this in a server text channel.", ephemeral=True)
            overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
            overwrite.send_messages = False if locked else None
            try:
                await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=f"{'Locked' if locked else 'Unlocked'} by {interaction.user}")
                await interaction.response.send_message("🔒 Channel locked." if locked else "🔓 Channel unlocked.", ephemeral=True)
                await self.log(interaction.guild, "Channel permissions changed", f"{interaction.channel.mention} {'locked' if locked else 'unlocked'}.", interaction.user)
            except discord.Forbidden:
                await interaction.response.send_message("I need Manage Channels permission.", ephemeral=True)

        @tree.command(name="lock", description="Prevent @everyone from sending messages here")
        @app_commands.default_permissions(manage_channels=True)
        @app_commands.checks.has_permissions(manage_channels=True)
        async def lock(interaction: discord.Interaction):
            await set_lock(interaction, True)

        @tree.command(name="unlock", description="Allow @everyone to send messages here again")
        @app_commands.default_permissions(manage_channels=True)
        @app_commands.checks.has_permissions(manage_channels=True)
        async def unlock(interaction: discord.Interaction):
            await set_lock(interaction, False)

        @tree.command(name="warn", description="Send a moderation warning to a member")
        @app_commands.default_permissions(moderate_members=True)
        @app_commands.checks.has_permissions(moderate_members=True)
        async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
            error = self.hierarchy_error(interaction, member)
            if error:
                return await interaction.response.send_message(error, ephemeral=True)
            warning_id = self.users.add_warning(interaction.guild_id, member.id, interaction.user.id, reason) if self.users else None
            try:
                await member.send(f"You received a moderation warning in **{interaction.guild.name}**.\nReason: {reason}")
                dm_status = "DM delivered"
            except discord.Forbidden:
                dm_status = "DM closed; warning logged only"
            await self.log(interaction.guild, "Member warned", f"{member.mention} ({member.id})\nReason: {reason}\n{dm_status}", interaction.user)
            suffix = f" Warning ID: #{warning_id}." if warning_id else ""
            await interaction.response.send_message(f"⚠️ Warning processed for **{member}** ({dm_status}).{suffix}", ephemeral=True)
