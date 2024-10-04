"""
Main entry point for the Discord bot.

This module initializes and runs the Discord bot. It sets up the bot's configuration,
plugins, cogs, and backup system. The bot can be run standalone or controlled via a GUI.

Usage:
    To run the bot directly:
    $ python main.py
"""

import os
import sys
import asyncio
import signal
import time
import psutil
import discord
from dotenv import load_dotenv
from discord.ext import commands
import logging
from typing import Optional

from utils.config_manager import ConfigManager
from utils.custom_exceptions import ConfigurationError
from utils.plugin_manager import PluginManager
from utils.backup_manager import BackupManager
from utils.metrics import MetricsCollector

# Ensure the bot package directory is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Load environment variables from .env file
dotenv_path = os.path.join(project_root, '.env')
load_dotenv(dotenv_path)

# Initialize configuration
config = ConfigManager('bot_config.yaml')

# Access configuration values with defaults
discord_token = os.getenv('DISCORD_TOKEN') or config.discord.get('token')
if not discord_token:
    raise ConfigurationError("Discord token is required to run the bot.")

class DiscordBot:
    """
    Main bot class that encapsulates all bot functionality.
    """

    def __init__(self, status_callback=None):
        """Initialize the bot, plugin manager, and backup manager."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        intents.guilds = True

        command_prefix = config.discord.get('prefix', '!')
        self.bot = commands.AutoShardedBot(
            command_prefix=command_prefix,
            description=config.bot.get('description', 'A Discord Bot'),
            intents=intents,
            shard_count=config.discord.get('shard_count', None)
        )

        self.config = config
        self.plugin_manager = PluginManager(self.bot)
        self.backup_manager = BackupManager(self.config)
        self.metrics = MetricsCollector()
        self.start_time = time.time()
        self.status_callback = status_callback
        self.setup_logging()
        self.register_events()
        self.bot.config = self.config  # Make config accessible in cogs

    def setup_logging(self):
        """Set up logging for the bot."""
        log_file = self.config.logging.get('file', os.path.join(project_root, 'logs', 'bot.log'))
        log_level_str = self.config.logging.get('level', 'INFO').upper()
        log_level = getattr(logging, log_level_str, logging.INFO)

        os.makedirs(os.path.dirname(log_file), exist_ok=True)

        # Configure logging handlers with encoding
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )

        self.bot.logger = logging.getLogger('bot_logger')
        self.bot.logger.setLevel(log_level)
        self.bot.logger.addHandler(file_handler)
        self.bot.logger.addHandler(console_handler)
        self.bot.logger.info("Logger initialized.")

    def register_events(self):
        """Register bot event handlers."""

        @self.bot.event
        async def on_ready():
            """Event listener called when the bot is ready."""
            self.bot.logger.info(f'{self.bot.user} has connected to Discord!')
            self.bot.logger.info(f'Shard IDs: {self.bot.shard_ids}')
            await self.load_cogs()
            await self.plugin_manager.load_plugins()
            asyncio.create_task(self.backup_manager.run_periodic_backup())
            if self.status_callback:
                self.status_callback("Online")

        @self.bot.event
        async def on_message(message):
            """Process commands and record metrics."""
            if message.author.bot:
                return
            self.metrics.increment_message()
            await self.bot.process_commands(message)

        @self.bot.event
        async def on_command_completion(ctx):
            """Record successful command execution."""
            command_name = ctx.command.qualified_name
            self.metrics.increment_command(command_name)

        @self.bot.event
        async def on_command_error(ctx, error):
            """Handle command errors gracefully."""
            if hasattr(ctx.command, 'on_error'):
                return  # Skip if custom error handler is defined
            if isinstance(error, commands.CommandNotFound):
                await ctx.send("Command not found.")
            elif isinstance(error, commands.MissingRequiredArgument):
                await ctx.send("Missing arguments for the command.")
            elif isinstance(error, commands.CommandOnCooldown):
                await ctx.send(f"Command is on cooldown. Try again after {error.retry_after:.2f} seconds.")
            else:
                await ctx.send("An error occurred while processing the command.")
            self.bot.logger.error(f'Error in command {ctx.command}: {error}', exc_info=True)

    async def load_cogs(self):
        """Load all cogs from the cogs directory."""
        cogs_dir = os.path.join(current_dir, 'cogs')
        for filename in os.listdir(cogs_dir):
            if filename.endswith('.py') and not filename.startswith('__'):
                cog_name = filename[:-3]
                try:
                    await self.bot.load_extension(f'cogs.{cog_name}')
                    self.bot.logger.info(f'Loaded cog: {cog_name}')
                except Exception as e:
                    self.bot.logger.error(f'Failed to load cog {cog_name}: {e}', exc_info=True)

    async def start(self, token: Optional[str] = None):
        """
        Start the bot.

        Args:
            token (str, optional): The Discord bot token. If not provided, uses the token from config.
        """
        try:
            await self.bot.start(token or discord_token)
        except Exception as e:
            self.bot.logger.error(f'Error starting bot: {e}', exc_info=True)
            if self.status_callback:
                self.status_callback("Error")
            raise

    async def stop(self):
        """
        Stop the bot.

        This method safely shuts down the bot.
        """
        self.bot.logger.info("Shutting down bot...")
        await self.bot.close()
        await self.backup_manager.stop()
        self.bot.logger.info("Bot has been shut down.")

    def run(self):
        """
        Run the bot.

        This method starts the bot and handles the main event loop.
        It's used when running the bot standalone (not through GUI).
        """
        loop = asyncio.get_event_loop()

        def signal_handler():
            """Handle shutdown signals gracefully."""
            asyncio.create_task(self.stop())

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, signal_handler)
            except NotImplementedError:
                # Signal handlers are not implemented on Windows for ProactorEventLoop
                pass

        try:
            loop.run_until_complete(self.start(discord_token))
        except KeyboardInterrupt:
            self.bot.logger.info("Bot interrupted by user.")
        finally:
            loop.run_until_complete(self.stop())
            loop.close()

    def get_uptime(self) -> float:
        """Get the bot's uptime in seconds."""
        return time.time() - self.start_time

    def get_memory_usage(self) -> float:
        """Get the bot's current memory usage in MB."""
        process = psutil.Process()
        return process.memory_info().rss / 1024 / 1024  # Convert bytes to MB

    def get_cpu_usage(self) -> float:
        """Get the bot's current CPU usage percentage."""
        process = psutil.Process()
        return process.cpu_percent(interval=1.0)

    def get_disk_io_usage(self) -> float:
        """Get the bot's disk I/O usage in bytes per second."""
        disk_io = psutil.disk_io_counters()
        # Calculate bytes per second since boot
        system_uptime = time.time() - psutil.boot_time()
        return (disk_io.read_bytes + disk_io.write_bytes) / system_uptime if system_uptime > 0 else 0.0

    def get_network_usage(self) -> float:
        """Get the bot's network usage in bytes per second."""
        net_io = psutil.net_io_counters()
        # Calculate bytes per second since boot
        system_uptime = time.time() - psutil.boot_time()
        return (net_io.bytes_sent + net_io.bytes_recv) / system_uptime if system_uptime > 0 else 0.0

    def get_thread_performance(self) -> dict:
        """Get per-thread CPU usage."""
        thread_performance = {}
        try:
            process = psutil.Process()
            threads = process.threads()
            for thread in threads:
                thread_id = thread.id
                # Note: psutil does not provide per-thread CPU percent directly.
                # Instead, we can track CPU times.
                thread_performance[thread_id] = thread.user_time + thread.system_time
        except psutil.NoSuchProcess:
            self.bot.logger.error("Process no longer exists while fetching thread performance.")
        except Exception as e:
            self.bot.logger.error(f"Unexpected error while fetching thread performance: {e}", exc_info=True)
        return thread_performance

if __name__ == "__main__":
    try:
        # Set PYTHONIOENCODING to handle Unicode characters in console output
        os.environ['PYTHONIOENCODING'] = 'utf-8'
        bot_instance = DiscordBot()
        bot_instance.run()
    except ConfigurationError as ce:
        print(f"Configuration Error: {ce}")
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)