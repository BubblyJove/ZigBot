"""
Admin Commands Cog for Discord Bot.

This module provides administrative commands for managing the bot and server.
It includes commands for managing users, roles, channels, and more.

This cog is automatically loaded by the bot on startup.
"""

import discord
from discord.ext import commands
from utils.custom_exceptions import CommandError
import logging

class AdminCommands(commands.Cog):
    """
    Cog for administrative commands.
    
    Provides a set of commands that can be used by administrators to manage the bot and the server.
    """

    def __init__(self, bot):
        """
        Initialize the AdminCommands cog.

        Args:
            bot (commands.Bot): The bot instance.
        """
        self.bot = bot
        self.logger = logging.getLogger('admin_commands')

    @commands.command(name='kick')
    @commands.has_permissions(kick_members=True)
    async def kick_member(self, ctx, member: discord.Member, *, reason: str = None):
        """
        Kick a member from the server.

        Usage:
            !kick @member [reason]

        Args:
            ctx (commands.Context): The invocation context.
            member (discord.Member): The member to kick.
            reason (str, optional): The reason for kicking.
        """
        try:
            await member.kick(reason=reason)
            await ctx.send(f"{member} has been kicked from the server.")
            self.logger.info(f"{ctx.author} kicked {member} | Reason: {reason}")
        except discord.Forbidden:
            self.logger.error(f"Permission error while trying to kick {member}.")
            await ctx.send("I don't have permission to kick that user.")
        except Exception as e:
            self.logger.error(f"Error kicking member: {e}", exc_info=True)
            raise CommandError(f"An error occurred while trying to kick {member}.")

    @commands.command(name='ban')
    @commands.has_permissions(ban_members=True)
    async def ban_member(self, ctx, member: discord.Member, *, reason: str = None):
        """
        Ban a member from the server.

        Usage:
            !ban @member [reason]

        Args:
            ctx (commands.Context): The invocation context.
            member (discord.Member): The member to ban.
            reason (str, optional): The reason for banning.
        """
        try:
            await member.ban(reason=reason)
            await ctx.send(f"{member} has been banned from the server.")
            self.logger.info(f"{ctx.author} banned {member} | Reason: {reason}")
        except discord.Forbidden:
            self.logger.error(f"Permission error while trying to ban {member}.")
            await ctx.send("I don't have permission to ban that user.")
        except Exception as e:
            self.logger.error(f"Error banning member: {e}", exc_info=True)
            raise CommandError(f"An error occurred while trying to ban {member}.")

    @commands.command(name='unban')
    @commands.has_permissions(ban_members=True)
    async def unban_member(self, ctx, *, user_name: str):
        """
        Unban a user from the server.

        Usage:
            !unban username#discriminator

        Args:
            ctx (commands.Context): The invocation context.
            user_name (str): The full username and discriminator (e.g., User#1234).
        """
        try:
            banned_users = await ctx.guild.bans()
            user_name, user_discriminator = user_name.split('#')

            for ban_entry in banned_users:
                user = ban_entry.user
                if (user.name, user.discriminator) == (user_name, user_discriminator):
                    await ctx.guild.unban(user)
                    await ctx.send(f"Unbanned {user.mention}.")
                    self.logger.info(f"{ctx.author} unbanned {user}.")
                    return

            await ctx.send(f"User {user_name}#{user_discriminator} not found in banned users.")
        except Exception as e:
            self.logger.error(f"Error unbanning member: {e}", exc_info=True)
            raise CommandError("An error occurred while trying to unban the user.")

    @commands.command(name='mute')
    @commands.has_permissions(manage_roles=True)
    async def mute_member(self, ctx, member: discord.Member, *, reason: str = None):
        """
        Mute a member in the server.

        Usage:
            !mute @member [reason]

        Args:
            ctx (commands.Context): The invocation context.
            member (discord.Member): The member to mute.
            reason (str, optional): The reason for muting.
        """
        try:
            mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
            if not mute_role:
                # Create a Muted role if it doesn't exist
                mute_role = await ctx.guild.create_role(name="Muted")
                self.logger.debug("Muted role created.")

                # Set permissions for the role in each channel
                for channel in ctx.guild.channels:
                    await channel.set_permissions(mute_role, speak=False, send_messages=False, read_message_history=True, read_messages=False)
                    self.logger.debug(f"Permissions set for Muted role in channel: {channel.name}")

            await member.add_roles(mute_role, reason=reason)
            await ctx.send(f"{member} has been muted.")
            self.logger.info(f"{ctx.author} muted {member} | Reason: {reason}")
        except discord.Forbidden:
            self.logger.error(f"Permission error while trying to mute {member}.")
            await ctx.send("I don't have permission to mute that user.")
        except Exception as e:
            self.logger.error(f"Error muting member: {e}", exc_info=True)
            raise CommandError(f"An error occurred while trying to mute {member}.")

    @commands.command(name='unmute')
    @commands.has_permissions(manage_roles=True)
    async def unmute_member(self, ctx, member: discord.Member):
        """
        Unmute a member in the server.

        Usage:
            !unmute @member

        Args:
            ctx (commands.Context): The invocation context.
            member (discord.Member): The member to unmute.
        """
        try:
            mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
            if mute_role in member.roles:
                await member.remove_roles(mute_role)
                await ctx.send(f"{member} has been unmuted.")
                self.logger.info(f"{ctx.author} unmuted {member}.")
            else:
                await ctx.send(f"{member} is not muted.")
        except discord.Forbidden:
            self.logger.error(f"Permission error while trying to unmute {member}.")
            await ctx.send("I don't have permission to unmute that user.")
        except Exception as e:
            self.logger.error(f"Error unmuting member: {e}", exc_info=True)
            raise CommandError(f"An error occurred while trying to unmute {member}.")

    @commands.command(name='clear')
    @commands.has_permissions(manage_messages=True)
    async def clear_messages(self, ctx, amount: int):
        """
        Clear a number of messages in the current channel.

        Usage:
            !clear <amount>

        Args:
            ctx (commands.Context): The invocation context.
            amount (int): The number of messages to delete.
        """
        try:
            deleted = await ctx.channel.purge(limit=amount+1)  # Include the command message
            await ctx.send(f"Deleted {len(deleted)-1} messages.", delete_after=5)
            self.logger.info(f"{ctx.author} cleared {len(deleted)-1} messages in {ctx.channel}.")
        except discord.Forbidden:
            self.logger.error("Permission error while trying to clear messages.")
            await ctx.send("I don't have permission to delete messages.")
        except Exception as e:
            self.logger.error(f"Error clearing messages: {e}", exc_info=True)
            raise CommandError("An error occurred while trying to clear messages.")

    @commands.command(name='announce')
    @commands.has_permissions(administrator=True)
    async def make_announcement(self, ctx, *, message: str):
        """
        Make an announcement in the announcement channel.

        Usage:
            !announce <message>

        Args:
            ctx (commands.Context): The invocation context.
            message (str): The announcement message.
        """
        try:
            announcement_channel_name = getattr(self.bot.config.bot, 'announcement_channel', 'announcements')
            channel = discord.utils.get(ctx.guild.text_channels, name=announcement_channel_name)
            if channel:
                await channel.send(message)
                await ctx.send("Announcement sent.")
                self.logger.info(f"{ctx.author} made an announcement: {message}")
            else:
                await ctx.send(f"Announcement channel '{announcement_channel_name}' not found.")
        except Exception as e:
            self.logger.error(f"Error making announcement: {e}", exc_info=True)
            raise CommandError("An error occurred while trying to make an announcement.")

async def setup(bot):
    """Asynchronous setup for the AdminCommands cog."""
    await bot.add_cog(AdminCommands(bot))