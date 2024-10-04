# utils/backup_manager.py

"""
Backup Manager for Discord Bot.

This module provides functionality for creating and managing backups of bot data.
It includes a BackupManager class that handles periodic backups.
"""

import asyncio
import zipfile
import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

from utils.config_manager import ConfigManager, ConfigSection
from utils.custom_exceptions import BackupError
import aiofiles
import shutil

class BackupManager:
    """
    A class for managing bot data backups.

    This class handles the creation of periodic backups of specified bot data files.
    """

    def __init__(self, config: ConfigManager):
        """
        Initialize the BackupManager.

        Args:
            config (ConfigManager): The bot's configuration manager instance.
        """
        self.config = config
        backup_config = getattr(self.config, 'backup', {})
        if isinstance(backup_config, ConfigSection):
            backup_config = backup_config.to_dict()

        self.backup_dir = backup_config.get('directory', 'backups')
        self.backup_interval = backup_config.get('interval', 24) * 3600  # Default to 24 hours
        self.backup_files = backup_config.get('files', [])
        self.max_backups = backup_config.get('max_backups', 10)
        self.max_backup_age = backup_config.get('max_backup_age', 7)  # Days

        # Validate backup directory
        if not isinstance(self.backup_dir, str) or not self.backup_dir:
            raise BackupError("Invalid backup directory specified in configuration.")

        os.makedirs(self.backup_dir, exist_ok=True)
        self.logger = logging.getLogger('backup_manager')
        self._stop_event = asyncio.Event()

    async def create_backup(self) -> None:
        """
        Create a backup of the bot's data.

        This method creates a zip file containing all specified backup files.
        The backup is saved in the configured backup directory with a timestamp.

        Raises:
            BackupError: If there's an error during the backup process.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_{timestamp}.zip"
        backup_path = os.path.join(self.backup_dir, backup_filename)

        try:
            await self._write_backup(backup_path)
            self.logger.info(f"Backup created: {backup_filename}")
        except Exception as e:
            self.logger.error(f"Failed to create backup: {e}", exc_info=True)
            raise BackupError(f"Failed to create backup: {e}") from e

    async def _write_backup(self, backup_path: str):
        """Asynchronous method to write backup using aiofiles and zipfile."""
        loop = asyncio.get_event_loop()
        async with aiofiles.tempfile.TemporaryDirectory() as temp_dir:
            # Copy files to temporary directory
            for file_path in self.backup_files:
                if os.path.exists(file_path):
                    dest_path = os.path.join(temp_dir, os.path.basename(file_path))
                    await loop.run_in_executor(None, shutil.copy2, file_path, dest_path)
                    self.logger.info(f"Added {file_path} to backup.")
                else:
                    self.logger.warning(f"File not found: {file_path}")

            # Create zip archive from the temporary directory
            await loop.run_in_executor(None, shutil.make_archive, backup_path.replace('.zip', ''), 'zip', temp_dir)

    async def run_periodic_backup(self) -> None:
        """
        Run periodic backups.

        This method runs in the background, creating backups at the interval
        specified in the configuration. It continues running until stopped.
        """
        while not self._stop_event.is_set():
            try:
                await self.create_backup()
                await self.cleanup_old_backups()
            except Exception as e:
                self.logger.error(f"Error in periodic backup: {e}", exc_info=True)
            try:
                # Wait for the backup interval or until stop event is set
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.backup_interval)
            except asyncio.TimeoutError:
                continue  # Timeout means it's time to perform the next backup

    async def stop(self):
        """
        Stop the periodic backup task.
        """
        self._stop_event.set()

    async def list_backups(self) -> List[str]:
        """
        List all available backups.

        Returns:
            List[str]: A list of backup filenames.
        """
        try:
            backups = [
                f for f in os.listdir(self.backup_dir)
                if f.startswith("backup_") and f.endswith(".zip")
            ]
            backups.sort(reverse=True)
            return backups
        except Exception as e:
            self.logger.error(f"Failed to list backups: {e}", exc_info=True)
            raise BackupError(f"Failed to list backups: {e}") from e

    async def restore_backup(self, backup_filename: str) -> None:
        """
        Restore a specific backup.

        Args:
            backup_filename (str): The filename of the backup to restore.

        Raises:
            BackupError: If there's an error during the restore process.
        """
        backup_path = os.path.join(self.backup_dir, backup_filename)
        try:
            await self._restore_backup(backup_path)
            self.logger.info(f"Backup restored: {backup_filename}")
        except Exception as e:
            self.logger.error(f"Failed to restore backup: {e}", exc_info=True)
            raise BackupError(f"Failed to restore backup: {e}") from e

    async def _restore_backup(self, backup_path: str):
        """Asynchronous method to restore backup using aiofiles and zipfile."""
        loop = asyncio.get_event_loop()
        with zipfile.ZipFile(backup_path, 'r') as backup_zip:
            await loop.run_in_executor(None, backup_zip.extractall, self.backup_dir)

    async def cleanup_old_backups(self) -> None:
        """
        Remove old backups based on max_backups and max_backup_age.
        """
        try:
            backups = await self.list_backups()
            # Remove backups exceeding max_backups
            for old_backup in backups[self.max_backups:]:
                os.remove(os.path.join(self.backup_dir, old_backup))
                self.logger.info(f"Removed old backup: {old_backup}")

            # Remove backups older than max_backup_age
            cutoff_date = datetime.now() - timedelta(days=self.max_backup_age)
            for backup in backups:
                backup_path = os.path.join(self.backup_dir, backup)
                modified_time = datetime.fromtimestamp(os.path.getmtime(backup_path))
                if modified_time < cutoff_date:
                    os.remove(backup_path)
                    self.logger.info(f"Removed expired backup: {backup}")
        except Exception as e:
            self.logger.error(f"Failed to clean up old backups: {e}", exc_info=True)
            raise BackupError(f"Failed to clean up old backups: {e}") from e