# cogs/censorship.py

import discord
from discord.ext import commands, tasks
import logging
import os
import re
import sqlite3
import time
import asyncio
from typing import List, Dict

from utils.custom_exceptions import ThreadManagementError
from utils.metrics import MetricsCollector
from utils.config_manager import ConfigManager

# NLP and Phonetic Libraries
import nltk
from nltk.stem import PorterStemmer
import enchant  # For dictionary lookup
from collections import defaultdict
import json

nltk.download('punkt', quiet=True)

class Censorship(commands.Cog):
    """
    Cog for managing content moderation and censorship.

    This cog uses NLP techniques, phonetic algorithms, and Bayesian filtering to detect
    and handle messages containing inappropriate content. It schedules messages
    for deletion after a configurable delay and announces infractions in an admin channel.
    """

    def __init__(self, bot):
        """
        Initialize the Censorship cog.

        Args:
            bot (commands.Bot): The bot instance.
        """
        self.bot = bot
        self.config = bot.config
        self.logger = logging.getLogger('censorship')

        # Set the deletion delay (in seconds) with default
        self.delay = getattr(self.config.censorship, 'deletion_delay', 6) * 3600  # Default to 6 hours

        # Admin channel ID from config
        self.admin_channel_id = getattr(self.config.discord, 'admin_channel_id', None)

        # Load banned words and exceptions
        self.banned_words = set()
        self.exceptions = set()
        asyncio.create_task(self.load_banned_words())

        # Initialize NLP components
        self.ps = PorterStemmer()
        self.dictionary = enchant.Dict("en_US")

        # Phonetic mapping using Soundex algorithm
        self.soundex_codes = {}

        # Initialize Bayesian filter data
        self.ham_counts = defaultdict(int)
        self.spam_counts = defaultdict(int)
        self.total_ham = 0
        self.total_spam = 0
        self.load_training_data()

        # Set up the SQLite database for infractions
        self.setup_database()

        # Start the background task for deleting expired messages
        self.delete_expired_messages.start()

    def cog_unload(self):
        """Cancel the background tasks and close the database when the cog is unloaded."""
        self.delete_expired_messages.cancel()
        if hasattr(self, 'conn'):
            self.conn.close()

    async def load_banned_words(self):
        """
        Load banned words and exceptions, and prepare data structures.
        """
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
            data_dir = os.path.join(project_root, 'data')
            banned_words_file = os.path.join(data_dir, 'banned_words.txt')
            exceptions_file = os.path.join(data_dir, 'exceptions.txt')

            # Load banned words asynchronously
            self.banned_words = await self.load_words_from_file(banned_words_file)
            self.exceptions = await self.load_words_from_file(exceptions_file)

            # Remove exceptions from banned words
            self.banned_words -= self.exceptions

            # Create Soundex codes
            self.soundex_codes = self.create_soundex_codes(self.banned_words)

            self.logger.info(f"Loaded {len(self.banned_words)} banned words and {len(self.exceptions)} exceptions.")

        except Exception as e:
            self.logger.error(f"Failed to load banned words: {e}", exc_info=True)

    async def load_words_from_file(self, file_path: str) -> set:
        """
        Load words from a file asynchronously.

        Args:
            file_path (str): The path to the file.

        Returns:
            set: A set of words loaded from the file.
        """
        words = set()
        if os.path.exists(file_path):
            from aiofile import async_open
            async with async_open(file_path, 'r', encoding='utf-8') as f:
                async for line in f:
                    word = line.strip()
                    if word and not word.startswith('#'):
                        words.add(word.lower())
        else:
            self.logger.warning(f"File not found: {file_path}")
        return words

    def create_soundex_codes(self, words: set) -> Dict[str, str]:
        """
        Create a mapping of words to their Soundex codes.

        Args:
            words (set): Set of words to generate Soundex codes for.

        Returns:
            dict: Mapping of words to their Soundex codes.
        """
        soundex_mapping = {}
        for word in words:
            code = self.soundex(word)
            soundex_mapping[word] = code
        return soundex_mapping

    def soundex(self, word: str) -> str:
        """
        Compute the Soundex code for a word.

        Args:
            word (str): The word to compute Soundex code for.

        Returns:
            str: The Soundex code.
        """
        word = word.upper()
        codes = ("BFPV", "CGJKQSXZ", "DT", "L", "MN", "R")
        soundex_dict = {}
        for code, letters in enumerate(codes, 1):
            for letter in letters:
                soundex_dict[letter] = str(code)

        soundex_code = [word[0]]
        for char in word[1:]:
            digit = soundex_dict.get(char, '0')
            if digit != soundex_code[-1]:
                soundex_code.append(digit)

        soundex_code = ''.join(soundex_code).replace('0', '')
        soundex_code = (soundex_code + '0000')[:4]
        return soundex_code

    def load_training_data(self):
        """
        Load or initialize training data for Bayesian filtering.
        """
        try:
            data_file = os.path.join('data', 'training_data.json')
            if os.path.exists(data_file):
                with open(data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.ham_counts = defaultdict(int, data.get('ham_counts', {}))
                    self.spam_counts = defaultdict(int, data.get('spam_counts', {}))
                    self.total_ham = data.get('total_ham', 0)
                    self.total_spam = data.get('total_spam', 0)
                    self.logger.info("Loaded training data for Bayesian filtering.")
            else:
                self.logger.warning(f"Training data file {data_file} not found. Starting with empty data.")

        except Exception as e:
            self.logger.error(f"Error loading training data: {e}", exc_info=True)

    def setup_database(self):
        """Set up the SQLite database for storing infractions."""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
            db_path = os.path.join(project_root, 'data', 'infractions.db')
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            self.conn = sqlite3.connect(db_path)
            self.cursor = self.conn.cursor()
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS infractions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    deletion_time REAL NOT NULL,
                    content TEXT NOT NULL
                )
            ''')
            self.conn.commit()
            self.logger.info("Infractions database setup completed.")
        except Exception as e:
            self.logger.error(f"Failed to set up infractions database: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_message(self, message):
        """
        Event listener called when a message is sent in any channel the bot can see.

        This method checks each message using advanced techniques and
        schedules it for deletion if it contains any banned content.

        Args:
            message (discord.Message): The message to check.
        """
        if message.author.bot:
            return

        # Log that on_message is triggered
        self.logger.debug(f"Processing message ID {message.id} from {message.author} in channel {message.channel}.")

        try:
            content = message.content.lower()
            is_inappropriate = self.check_message(content)

            if is_inappropriate:
                # Schedule the message for deletion
                deletion_time = time.time() + self.delay
                self.store_infraction(message, deletion_time)

                # Announce the infraction in the admin channel
                await self.announce_infraction(message)

                # Optionally schedule deletion after delay
                await asyncio.sleep(self.delay)
                try:
                    await message.delete()
                    self.logger.info(f"Deleted message ID {message.id} from {message.author}.")
                except discord.Forbidden:
                    self.logger.error(f"Missing permissions to delete message ID {message.id}.")
                except discord.NotFound:
                    self.logger.warning(f"Message ID {message.id} not found. It might have been deleted already.")
                except Exception as e:
                    self.logger.error(f"Error deleting message ID {message.id}: {e}", exc_info=True)

        except Exception as e:
            self.logger.error(f"Error handling message ID {message.id}: {e}", exc_info=True)

    def check_message(self, content: str) -> bool:
        """
        Check if the message contains inappropriate content.

        Args:
            content (str): The content of the message.

        Returns:
            bool: True if inappropriate, False otherwise.
        """
        tokens = self.tokenize(content)
        stemmed_tokens = [self.ps.stem(token) for token in tokens]

        # Check against banned words using stemming
        for token in stemmed_tokens:
            if token in self.banned_words:
                self.logger.debug(f"Token '{token}' found in banned words.")
                return True

        # Check using phonetic matching
        for token in tokens:
            soundex_code = self.soundex(token)
            if soundex_code in self.soundex_codes.values():
                self.logger.debug(f"Token '{token}' matches banned words phonetically.")
                return True

        # Check using Bayesian filter
        spam_probability = self.calculate_spam_probability(tokens)
        if spam_probability > 0.9:
            self.logger.debug(f"Message classified as inappropriate with probability {spam_probability}.")
            return True

        return False

    def tokenize(self, text: str) -> List[str]:
        """
        Tokenize the text into words, considering various obfuscations.

        Args:
            text (str): The text to tokenize.

        Returns:
            list: List of tokens.
        """
        # Use NLTK's word tokenizer
        tokens = nltk.word_tokenize(text)
        return tokens

    def calculate_spam_probability(self, tokens: List[str]) -> float:
        """
        Calculate the probability that a message is spam using Bayesian filtering.

        Args:
            tokens (list): List of tokens from the message.

        Returns:
            float: Spam probability.
        """
        spam_likelihood = ham_likelihood = 1.0

        for token in tokens:
            spam_count = self.spam_counts.get(token, 0.0)
            ham_count = self.ham_counts.get(token, 0.0)

            # Apply Laplace smoothing
            p_token_spam = (spam_count + 1) / (self.total_spam + 2)
            p_token_ham = (ham_count + 1) / (self.total_ham + 2)

            spam_likelihood *= p_token_spam
            ham_likelihood *= p_token_ham

        # Avoid division by zero
        if spam_likelihood + ham_likelihood == 0:
            return 0.0

        spam_probability = spam_likelihood / (spam_likelihood + ham_likelihood)
        return spam_probability

    def store_infraction(self, message, deletion_time):
        """Store the infraction in the database."""
        try:
            self.cursor.execute('''
                INSERT INTO infractions (message_id, channel_id, user_id, timestamp, deletion_time, content)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                str(message.id),
                str(message.channel.id),
                str(message.author.id),
                message.created_at.timestamp(),
                deletion_time,
                message.content,
            ))
            self.conn.commit()
            self.logger.info(f"Stored infraction for message ID {message.id} by user {message.author}.")
        except Exception as e:
            self.logger.error(f"Error storing infraction for message ID {message.id}: {e}", exc_info=True)

    async def announce_infraction(self, message):
        """
        Announce the infraction in the admin channel.

        Args:
            message (discord.Message): The message that triggered the infraction.
        """
        try:
            if not self.admin_channel_id:
                self.admin_channel_id = getattr(self.config.discord, 'admin_channel_id', None)
                if not self.admin_channel_id:
                    self.logger.warning("Admin channel ID not set. Infraction not announced.")
                    return

            admin_channel = self.bot.get_channel(int(self.admin_channel_id))
            if admin_channel:
                embed = discord.Embed(
                    title="Recorded Infraction",
                    color=discord.Color.orange(),
                    timestamp=discord.utils.utcnow()
                )
                embed.add_field(name="User", value=f"{message.author} (ID: {message.author.id})", inline=False)
                embed.add_field(name="Server", value=message.guild.name, inline=False)
                embed.add_field(name="Channel", value=message.channel.mention, inline=False)
                embed.add_field(name="Message Content", value=message.content, inline=False)
                embed.add_field(name="Scheduled Deletion", value=f"In {self.delay / 3600} hours", inline=False)
                await admin_channel.send(embed=embed)
                self.logger.info(f"Announced infraction for message ID {message.id} in admin channel.")
            else:
                self.logger.warning(f"Admin channel with ID {self.admin_channel_id} not found.")
        except Exception as e:
            self.logger.error(f"Error announcing infraction for message ID {message.id}: {e}", exc_info=True)

    @tasks.loop(seconds=60)
    async def delete_expired_messages(self):
        """Delete messages whose scheduled deletion time has passed."""
        try:
            current_time = time.time()
            self.cursor.execute('''
                SELECT id, message_id, channel_id FROM infractions WHERE deletion_time <= ?
            ''', (current_time,))
            rows = self.cursor.fetchall()

            for row in rows:
                infraction_id, message_id, channel_id = row
                channel = self.bot.get_channel(int(channel_id))
                if channel:
                    try:
                        message = await channel.fetch_message(int(message_id))
                        await message.delete()
                        self.logger.info(f"Deleted message ID {message_id} from channel ID {channel_id}.")
                    except discord.NotFound:
                        self.logger.warning(f"Message ID {message_id} not found. It might have been deleted already.")
                    except discord.Forbidden:
                        self.logger.error(f"Missing permissions to delete message ID {message_id} in channel ID {channel_id}.")
                    except Exception as e:
                        self.logger.error(f"Error deleting message ID {message_id}: {e}", exc_info=True)
                else:
                    self.logger.warning(f"Channel ID {channel_id} not found.")

                # Remove the infraction from the database
                self.cursor.execute('DELETE FROM infractions WHERE id = ?', (infraction_id,))
                self.conn.commit()

        except Exception as e:
            self.logger.error(f"Error deleting expired messages: {e}", exc_info=True)

    @delete_expired_messages.before_loop
    async def before_delete_expired_messages(self):
        """Wait for the bot to be ready before starting the deletion loop."""
        await self.bot.wait_until_ready()

    # Removed the duplicate setadminchannel command from this cog.

    @commands.command(name='reloadbannedwords')
    @commands.has_permissions(administrator=True)
    async def reload_banned_words(self, ctx):
        """
        Reload the banned words from the file.

        Usage:
            !reloadbannedwords

        Args:
            ctx (commands.Context): The invocation context.
        """
        try:
            await self.load_banned_words()
            await ctx.send("Banned words have been reloaded.")
            self.logger.info("Banned words have been reloaded by admin.")
        except Exception as e:
            self.logger.error(f"Error reloading banned words: {e}", exc_info=True)
            await ctx.send("An error occurred while reloading banned words.")

    @commands.command(name='addbannedword')
    @commands.has_permissions(administrator=True)
    async def add_banned_word(self, ctx, *, word: str):
        """
        Add a new word to the banned words list.

        Usage:
            !addbannedword <word>

        Args:
            ctx (commands.Context): The invocation context.
            word (str): The word to add to the banned list.
        """
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
            banned_words_file = os.path.join(project_root, 'data', 'banned_words.txt')

            from aiofile import async_open
            async with async_open(banned_words_file, 'a', encoding='utf-8') as f:
                await f.write(f"{word}\n")

            await self.load_banned_words()
            await ctx.send(f"Added `{word}` to the banned words list.")
            self.logger.info(f"Added '{word}' to banned words by {ctx.author}.")
        except Exception as e:
            self.logger.error(f"Error adding banned word '{word}': {e}", exc_info=True)
            await ctx.send("An error occurred while adding the banned word.")

    @commands.command(name='removebannedword')
    @commands.has_permissions(administrator=True)
    async def remove_banned_word(self, ctx, *, word: str):
        """
        Remove a word from the banned words list.

        Usage:
            !removebannedword <word>

        Args:
            ctx (commands.Context): The invocation context.
            word (str): The word to remove from the banned list.
        """
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
            banned_words_file = os.path.join(project_root, 'data', 'banned_words.txt')

            if not os.path.exists(banned_words_file):
                await ctx.send("Banned words file does not exist.")
                return

            from aiofile import async_open
            async with async_open(banned_words_file, 'r+', encoding='utf-8') as f:
                content = await f.read()
                words = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith('#')]

                if word.lower() not in [w.lower() for w in words]:
                    await ctx.send(f"The word `{word}` is not in the banned words list.")
                    return

                words = [w for w in words if w.lower() != word.lower()]
                await f.seek(0)
                await f.write('\n'.join(words) + '\n')
                await f.truncate()

            await self.load_banned_words()
            await ctx.send(f"Removed `{word}` from the banned words list.")
            self.logger.info(f"Removed '{word}' from banned words by {ctx.author}.")
        except Exception as e:
            self.logger.error(f"Error removing banned word '{word}': {e}", exc_info=True)
            await ctx.send("An error occurred while removing the banned word.")

async def setup(bot):
    """Asynchronous setup for the Censorship cog."""
    await bot.add_cog(Censorship(bot))