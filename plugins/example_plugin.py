"""
Example Plugin for Discord Bot.

This module demonstrates how to create a simple plugin for the bot.
It includes a basic command that responds with a greeting.
"""

from discord.ext import commands

class ExamplePlugin(commands.Cog):
    """
    An example plugin demonstrating basic bot functionality.
    """

    def __init__(self, bot):
        """
        Initialize the ExamplePlugin.

        Args:
            bot (commands.Bot): The bot instance.
        """
        self.bot = bot

    @commands.command()
    async def hello(self, ctx):
        """
        A simple command that greets the user.

        Usage:
            !hello

        Args:
            ctx (commands.Context): The invocation context.
        """
        await ctx.send(f"Hello, {ctx.author.mention}!")

async def setup(bot):
    """
    Set up the ExamplePlugin.

    This function is called by Discord.py when adding the cog to the bot.

    Args:
        bot (commands.Bot): The bot instance.
    """
    await bot.add_cog(ExamplePlugin(bot))