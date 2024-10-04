"""
Plugin Manager for Discord Bot.

This module provides functionality for loading, unloading, and managing bot plugins.
It includes a PluginManager class that handles plugin operations.
"""

import importlib
import yaml
from typing import Dict, Any, Optional
from discord.ext import commands
import os
import logging

from utils.custom_exceptions import PluginError

class PluginManager:
    """
    A class for managing bot plugins.

    This class handles the loading, unloading, and reloading of bot plugins.
    """

    def __init__(self, bot: commands.Bot):
        """
        Initialize the PluginManager.

        Args:
            bot (commands.Bot): The bot instance.
        """
        self.bot = bot
        self.plugins: Dict[str, Any] = {}
        self.logger = logging.getLogger('plugin_manager')

        # Load the plugin configuration from the YAML file
        self.plugin_config = self._load_plugin_config()
        self.plugin_directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'plugins')

    def _load_plugin_config(self) -> Dict[str, Any]:
        """
        Load the plugin configuration from the YAML file.

        Returns:
            Dict[str, Any]: The plugin configuration dictionary.

        Raises:
            PluginError: If the configuration file is missing or malformed.
        """
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
        config_path = os.path.join(project_root, 'config', 'plugins.yaml')
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            self.logger.warning(f"Plugin configuration file not found at {config_path}. Using default configuration.")
            return {'enabled_plugins': []}
        except yaml.YAMLError as e:
            raise PluginError(f"Error parsing plugin configuration: {e}")

    async def load_plugins(self):
        """
        Load all enabled plugins.

        Raises:
            PluginError: If there's an error loading a plugin.
        """
        enabled_plugins = self.plugin_config.get('enabled_plugins', [])
        for plugin_name in enabled_plugins:
            if plugin_name not in self.plugins:
                try:
                    await self.load_plugin(plugin_name)
                except PluginError as e:
                    self.logger.error(f"Failed to load plugin '{plugin_name}': {e}")

    async def load_plugin(self, plugin_name: str):
        """
        Load a specific plugin.

        Args:
            plugin_name (str): The name of the plugin to load.

        Raises:
            PluginError: If the plugin cannot be loaded.
        """
        if plugin_name in self.plugins:
            raise PluginError(f"Plugin '{plugin_name}' is already loaded.")
        module_name = f'plugins.{plugin_name}'
        try:
            module = importlib.import_module(module_name)
            importlib.reload(module)  # Ensure fresh import
            if hasattr(module, 'setup'):
                await module.setup(self.bot)
                self.plugins[plugin_name] = module
                self.logger.info(f"Loaded plugin: {plugin_name}")
            else:
                raise PluginError(f"Plugin '{plugin_name}' does not have a setup function.")
        except ImportError as e:
            raise PluginError(f"Failed to import plugin '{plugin_name}': {e}")
        except Exception as e:
            raise PluginError(f"Error loading plugin '{plugin_name}': {e}") from e

    async def unload_plugin(self, plugin_name: str):
        """
        Unload a specific plugin.

        Args:
            plugin_name (str): The name of the plugin to unload.

        Raises:
            PluginError: If the plugin is not loaded or fails to unload.
        """
        module = self.plugins.get(plugin_name)
        if not module:
            raise PluginError(f"Plugin '{plugin_name}' is not loaded.")
        try:
            # Remove all cogs associated with this plugin
            cogs_to_remove = [cog_name for cog_name, cog in self.bot.cogs.items() if cog.__module__ == module.__name__]
            for cog_name in cogs_to_remove:
                await self.bot.remove_cog(cog_name)

            del self.plugins[plugin_name]
            self.logger.info(f"Unloaded plugin: {plugin_name}")
        except Exception as e:
            raise PluginError(f"Failed to unload plugin '{plugin_name}': {e}") from e

    async def reload_plugin(self, plugin_name: str):
        """
        Reload a specific plugin.

        Args:
            plugin_name (str): The name of the plugin to reload.

        Raises:
            PluginError: If there's an error during the reload process.
        """
        await self.unload_plugin(plugin_name)
        importlib.invalidate_caches()
        try:
            await self.load_plugin(plugin_name)
            self.logger.info(f"Reloaded plugin: {plugin_name}")
        except PluginError as e:
            raise PluginError(f"Failed to reload plugin '{plugin_name}': {e}") from e

    def get_plugin(self, plugin_name: str) -> Optional[Any]:
        """
        Get a loaded plugin by name.

        Args:
            plugin_name (str): The name of the plugin to get.

        Returns:
            The plugin module if found, None otherwise.
        """
        return self.plugins.get(plugin_name)

    def list_plugins(self) -> Dict[str, str]:
        """
        List all available plugins and their status.

        Returns:
            Dict[str, str]: A dictionary with plugin names as keys and their status as values.
        """
        plugins = {}
        if os.path.exists(self.plugin_directory):
            for filename in os.listdir(self.plugin_directory):
                if filename.endswith('.py') and not filename.startswith('__'):
                    plugin_name = filename[:-3]
                    status = 'Loaded' if plugin_name in self.plugins else 'Not Loaded'
                    plugins[plugin_name] = status
        else:
            self.logger.warning(f"Plugins directory not found at {self.plugin_directory}")
        return plugins