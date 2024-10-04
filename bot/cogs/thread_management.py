# cogs/thread_management.py

import asyncio
import aiohttp
from discord.ext import commands, tasks
from utils.custom_exceptions import ThreadManagementError
from utils.metrics import MetricsCollector
from utils.config_manager import ConfigSection
import logging

class ThreadManagementCog(commands.Cog):
    """
    Cog for managing threads from external sources.
    """

    def __init__(self, bot):
        """
        Initialize the ThreadManagement cog.

        Args:
            bot (commands.Bot): The bot instance.
        """
        self.bot = bot
        self.config = bot.config

        # Set up logger
        self.logger = logging.getLogger('thread_management')
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            )
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

        # Initialize HTTP session
        self.session = aiohttp.ClientSession()

        # Start background tasks
        self.check_threads.start()

    def cog_unload(self):
        """Clean up resources when the cog is unloaded."""
        self.check_threads.cancel()
        asyncio.create_task(self.close_session())

    async def close_session(self):
        """Close the aiohttp session gracefully."""
        if not self.session.closed:
            await self.session.close()
            self.logger.info("HTTP session closed successfully.")

    @MetricsCollector.record_api_latency('4chan')
    async def fetch_catalog(self, board: str) -> list:
        """
        Fetch the catalog for a specific board.

        This method is decorated to record API latency for monitoring purposes.

        Args:
            board (str): The board to fetch the catalog for.

        Returns:
            list: The JSON response containing the catalog data.

        Raises:
            ThreadManagementError: If the catalog fetch fails.
        """
        url = f'https://a.4cdn.org/{board}/catalog.json'
        try:
            async with self.session.get(url, timeout=10) as response:
                if response.status != 200:
                    self.logger.error(f"Failed to fetch catalog for board {board}: HTTP {response.status}")
                    raise ThreadManagementError(f"Failed to fetch catalog for board {board}: HTTP {response.status}")
                return await response.json()
        except asyncio.TimeoutError:
            self.logger.error(f"Timeout while fetching catalog for board {board}")
            raise ThreadManagementError(f"Timeout while fetching catalog for board {board}")
        except Exception as e:
            self.logger.error(f"Error fetching catalog for board {board}: {e}")
            raise ThreadManagementError(f"Error fetching catalog for board {board}: {e}")

    async def process_channels(self):
        """
        Process all channels configured for thread management.

        This method creates tasks for processing each channel and runs them concurrently.

        Returns:
            list: Results from processing each channel.
        """
        channels_config = getattr(self.config, 'thread_management', {}).get('channels', {})
        if isinstance(channels_config, ConfigSection):
            channels = channels_config.to_dict()
        elif isinstance(channels_config, dict):
            channels = channels_config
        else:
            channels = {}

        tasks_list = [
            self.process_channel(channel_id, channel_data)
            for channel_id, channel_data in channels.items()
        ]
        return await asyncio.gather(*tasks_list, return_exceptions=True)

    async def process_channel(self, channel_id: str, channel_data: dict):
        """
        Process a single channel for thread management.

        This method handles the specific logic for managing threads in a single channel.

        Args:
            channel_id (str): The ID of the channel to process.
            channel_data (dict): Configuration data for the channel.

        Returns:
            dict: Results of processing the channel.

        Raises:
            ThreadManagementError: If processing fails.
        """
        try:
            board = channel_data['board']
            keywords = channel_data.get('keywords', [])
            following = channel_data.get('following', [])

            catalog = await self.fetch_catalog(board)

            new_threads = self.find_new_threads(catalog, keywords)
            updated_threads = self.update_existing_threads(catalog, following)

            results = {
                'new_threads': len(new_threads),
                'updated_threads': len(updated_threads),
            }

            # Post new threads to Discord
            for thread in new_threads:
                await self.post_new_thread(channel_id, board, thread)

            # Update existing threads if necessary
            for thread in updated_threads:
                await self.update_thread(channel_id, board, thread)

            # Update metrics
            MetricsCollector.set_active_threads(len(following))
            MetricsCollector.increment_message()
            MetricsCollector.increment_command('process_channel')
            return results
        except Exception as e:
            self.logger.error(f"Error processing channel {channel_id}: {e}")
            raise ThreadManagementError(f"Error processing channel {channel_id}: {e}")

    def find_new_threads(self, catalog: list, keywords: list) -> list:
        """
        Find new threads matching the specified keywords.

        Args:
            catalog (list): The catalog data.
            keywords (list): The list of keywords to search for.

        Returns:
            list: A list of threads that match the criteria.
        """
        new_threads = []
        for page in catalog:
            for thread in page.get('threads', []):
                comment = thread.get('com', '').lower()
                if any(keyword.lower() in comment for keyword in keywords):
                    new_threads.append(thread)
        return new_threads

    def update_existing_threads(self, catalog: list, following: list) -> list:
        """
        Update information for threads already being followed.

        Args:
            catalog (list): The catalog data.
            following (list): The list of thread IDs being followed.

        Returns:
            list: A list of updated threads.
        """
        updated_threads = []
        existing_thread_ids = set(following)
        for page in catalog:
            for thread in page.get('threads', []):
                if thread['no'] in existing_thread_ids:
                    updated_threads.append(thread)
        return updated_threads

    async def post_new_thread(self, channel_id: str, board: str, thread: dict):
        """
        Post information about a new thread to the Discord channel.

        Args:
            channel_id (str): Channel ID where to post the thread.
            board (str): The board of the thread.
            thread (dict): Thread data.
        """
        channel = self.bot.get_channel(int(channel_id))
        if channel:
            thread_url = f"https://boards.4channel.org/{board}/thread/{thread.get('no')}"
            try:
                await channel.send(f"🔔 **New thread found:** {thread_url}")
                self.logger.info(f"Posted new thread to channel {channel_id}: {thread_url}")
            except Exception as e:
                self.logger.error(f"Failed to post new thread to channel {channel_id}: {e}", exc_info=True)
        else:
            self.logger.error(f"Channel not found: {channel_id}")

    async def update_thread(self, channel_id: str, board: str, thread: dict):
        """
        Update information about an existing thread in the Discord channel.

        Args:
            channel_id (str): Channel ID where to update the thread.
            board (str): The board of the thread.
            thread (dict): Thread data.
        """
        # Placeholder for thread update logic.
        # Implement any specific updates you want to perform on existing threads.
        channel = self.bot.get_channel(int(channel_id))
        if channel:
            thread_url = f"https://boards.4channel.org/{board}/thread/{thread.get('no')}"
            try:
                await channel.send(f"🔄 **Thread Updated:** {thread_url} has a new post.")
                self.logger.info(f"Updated thread in channel {channel_id}: {thread_url}")
            except Exception as e:
                self.logger.error(f"Failed to post thread update to channel {channel_id}: {e}", exc_info=True)
        else:
            self.logger.error(f"Channel not found: {channel_id}")

    @tasks.loop(minutes=5.0)
    async def check_threads(self):
        """
        Background task to periodically check and update threads.

        This task runs every 5 minutes by default.
        """
        self.logger.info("Starting periodic thread check")
        try:
            results = await self.process_channels()
            # Filter out exceptions from results
            clean_results = [res for res in results if not isinstance(res, Exception)]
            self.logger.info(f"Thread check completed. Results: {clean_results}")
        except ThreadManagementError as e:
            self.logger.error(f"ThreadManagementError during thread check: {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"Unexpected error during thread check: {e}", exc_info=True)

    @check_threads.before_loop
    async def before_check_threads(self):
        """Wait for the bot to be ready before starting the thread check loop."""
        await self.bot.wait_until_ready()

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
            self.logger.error(f"Error in thread management command: {error}", exc_info=error)

async def setup(bot):
    """
    Set up the ThreadManagement cog.

    This function is called by Discord.py when adding the cog to the bot.

    Args:
        bot (commands.Bot): The bot instance.
    """
    try:
        await bot.add_cog(ThreadManagementCog(bot))
    except Exception as e:
        bot.logger.error(f"Failed to add ThreadManagementCog: {e}", exc_info=True)
        raise ThreadManagementError("Failed to add ThreadManagementCog") from e