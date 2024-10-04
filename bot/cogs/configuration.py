# cogs/configuration.py

import discord
from discord.ext import commands
import yaml
import os
import logging

from utils.custom_exceptions import ConfigurationError
from utils.config_manager import ConfigManager

class Configuration(commands.Cog):
    """
    Cog for managing bot configuration via commands.
    """

    def __init__(self, bot):
        """
        Initialize the Configuration cog.

        Args:
            bot (commands.Bot): The bot instance.
        """
        self.bot = bot
        self.config = bot.config
        self.logger = logging.getLogger('configuration')

    @commands.command(name='setprefix')
    @commands.has_permissions(administrator=True)
    async def set_prefix(self, ctx, prefix: str):
        """
        Set a new command prefix for the bot.

        Usage:
            !setprefix <new_prefix>
        """
        try:
            if len(prefix) > 5:
                await ctx.send("Prefix too long. Please choose a prefix with 5 or fewer characters.")
                return

            self.config.discord.set('prefix', prefix)
            await self.config.save()
            await ctx.send(f"Command prefix set to `{prefix}`.")
            self.logger.info(f"Command prefix changed to '{prefix}' by {ctx.author}.")

            # Dynamically update the bot's command prefix
            self.bot.command_prefix = prefix
        except Exception as e:
            self.logger.error(f"Error setting prefix: {e}", exc_info=True)
            await ctx.send("An error occurred while setting the new prefix.")

    @commands.command(name='setadminchannel')
    @commands.has_permissions(administrator=True)
    async def set_admin_channel(self, ctx, channel: discord.TextChannel):
        """
        Set the admin channel where infractions will be announced.

        Usage:
            !setadminchannel #channel_name
        """
        try:
            self.config.discord.set('admin_channel_id', str(channel.id))
            await self.config.save()
            await ctx.send(f"Admin channel set to {channel.mention}.")
            self.logger.info(f"Admin channel set to {channel.name} (ID: {channel.id}) by {ctx.author}.")
        except Exception as e:
            self.logger.error(f"Error setting admin channel: {e}", exc_info=True)
            await ctx.send("An error occurred while setting the admin channel.")

    @commands.command(name='showconfig')
    @commands.has_permissions(administrator=True)
    async def show_config(self, ctx):
        """
        Display the current configuration without sensitive information.

        Usage:
            !showconfig
        """
        try:
            safe_config = self.config.get_safe_config()
            config_text = yaml.dump(safe_config, default_flow_style=False)
            if len(config_text) > 2000:
                # Discord has a 2000 character limit for messages
                await ctx.send("Configuration is too long to display.")
            else:
                await ctx.send(f"```yaml\n{config_text}\n```")
        except Exception as e:
            self.logger.error(f"Error displaying configuration: {e}", exc_info=True)
            await ctx.send("An error occurred while displaying the configuration.")

    @commands.command(name='reloadconfig')
    @commands.has_permissions(administrator=True)
    async def reload_config(self, ctx):
        """
        Reload the bot's configuration from the configuration file.

        Usage:
            !reloadconfig
        """
        try:
            self.config = ConfigManager('bot_config.yaml')
            self.bot.config = self.config  # Update the bot's config reference
            await self.config.save()
            await ctx.send("Configuration reloaded successfully.")
            self.logger.info(f"Configuration reloaded by {ctx.author}.")
        except Exception as e:
            self.logger.error(f"Error reloading configuration: {e}", exc_info=True)
            await ctx.send("An error occurred while reloading the configuration.")

    async def cog_command_error(self, ctx, error):
        """
        Error handler for commands in this cog.

        Args:
            ctx (commands.Context): The invocation context.
            error (Exception): The error that occurred.
        """
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You don't have the required permissions to use this command.")
        elif isinstance(error, commands.CommandNotFound):
            await ctx.send("Command not found.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("Invalid argument provided.")
        else:
            await ctx.send(f"An unexpected error occurred: {error}")
            self.logger.error(f"Error in configuration command: {error}", exc_info=error)

async def setup(bot):
    """Asynchronous setup for the Configuration cog."""
    # Check if the cog is already loaded to prevent multiple registrations
    if 'Configuration' not in bot.cogs:
        await bot.add_cog(Configuration(bot))
    else:
        bot.logger.warning("Configuration cog is already loaded.")