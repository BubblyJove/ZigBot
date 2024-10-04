# utils/config_manager.py

import yaml
import os
import threading
import re
from typing import Any, Dict, Optional
from dotenv import load_dotenv

class ConfigSection:
    """
    A helper class for accessing configuration sections with attribute-style access.
    """

    __slots__ = ('_parent', '_data', '_name', '_config')

    def __init__(self, parent, data: Dict[str, Any], name: str, config_ref: Dict[str, Any]):
        self._parent = parent
        self._data = data
        self._name = name
        self._config = config_ref  # Reference to the main config dict
        self._parse_section(data)

    def _parse_section(self, section: Dict[str, Any]):
        for key, value in section.items():
            if isinstance(value, dict):
                setattr(self, key, ConfigSection(self, value, key, self._config))
            else:
                setattr(self, key, value)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value from this section.
        """
        return getattr(self, key, default)

    def set(self, key: str, value: Any):
        """
        Set a configuration value in this section.
        """
        setattr(self, key, value)
        self._data[key] = value
        # Update the main config dict
        current = self._config
        keys = self._get_hierarchy_keys()
        for k in keys:
            current = current.setdefault(k, {})
        current[key] = value

    def _get_hierarchy_keys(self):
        keys = []
        current = self
        while isinstance(current, ConfigSection):
            keys.insert(0, current._name)
            current = current._parent
        return keys

    def to_dict(self, sanitize_func=lambda x: x) -> Dict[str, Any]:
        """Convert the ConfigSection and its children to a dictionary."""
        result = {}
        for key in self._data:
            val = getattr(self, key)
            if isinstance(val, ConfigSection):
                result[key] = val.to_dict(sanitize_func)
            elif isinstance(val, dict):
                result[key] = {k: sanitize_func(v) for k, v in val.items()}
            elif isinstance(val, str) and 'token' in key.lower():
                result[key] = '***REDACTED***'
            else:
                result[key] = sanitize_func(val)
        return result

    def __getitem__(self, item):
        return self._data.get(item, None)

    def __repr__(self):
        return f"<ConfigSection {self._name}>"


class ConfigManager:
    """
    A class for managing bot configuration.
    """

    __slots__ = ('_config', '_config_filename', '_config_lock', '_sections', '_initialized')

    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        # Singleton pattern to ensure only one instance
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super(ConfigManager, cls).__new__(cls)
            return cls._instance

    def __init__(self, config_filename: str):
        """
        Initialize the ConfigManager.
        """
        # Avoid re-initialization in singleton
        if hasattr(self, '_initialized') and self._initialized:
            return

        self._initialized = True
        self._config_filename = config_filename
        self._config_lock = threading.Lock()
        self._sections = {}
        self.reload()

    def reload(self):
        """
        Reload configuration from the YAML file.
        """
        # Load environment variables from .env file
        load_dotenv()
        # Load environment variables into a dictionary
        self._env_vars = {key: os.getenv(key) for key in os.environ.keys()}

        # Determine the absolute path to the configuration file
        script_path = os.path.abspath(__file__)
        project_root = os.path.abspath(os.path.join(script_path, '..', '..'))
        config_path = os.path.join(project_root, 'config', self._config_filename)

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with self._config_lock:
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_dict = yaml.safe_load(f)
                if config_dict is None:
                    raise ValueError("Configuration file is empty or invalid.")

                # Replace environment variables and parse the configuration
                self._config = self._replace_env_variables(config_dict)
                self._parse_config(self._config)
            except yaml.YAMLError as e:
                raise yaml.YAMLError(f"Error parsing configuration file: {str(e)}") from e

    def _replace_env_variables(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively replace environment variables in the configuration dictionary.
        """
        for key, value in config.items():
            if isinstance(value, dict):
                config[key] = self._replace_env_variables(value)
            elif isinstance(value, str):
                # Replace environment variables in the form ${VARIABLE_NAME}
                config[key] = self._substitute_env_vars(value)
        return config

    def _substitute_env_vars(self, value: str) -> str:
        """
        Substitute environment variables in a string.
        """
        env_var_pattern = re.compile(r'\$\{(\w+)\}')
        matches = env_var_pattern.findall(value)
        for var in matches:
            env_value = os.getenv(var)
            if env_value is None:
                raise ValueError(f"Environment variable '{var}' not found.")
            value = value.replace(f'${{{var}}}', env_value)
        return value

    def _parse_config(self, config: Dict[str, Any]):
        """
        Recursively set attributes from the configuration dictionary.
        """
        for key, value in config.items():
            if isinstance(value, dict):
                section = ConfigSection(self, value, key, self._config)
                setattr(self, key, section)
                self._sections[key] = section
            else:
                setattr(self, key, value)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.
        """
        return getattr(self, key, default)

    def set(self, key: str, value: Any):
        """
        Set a configuration value.
        """
        setattr(self, key, value)
        self._config[key] = value

    async def save(self, config_filename: Optional[str] = None):
        """
        Save the current configuration back to the YAML file asynchronously.
        """
        if config_filename is None:
            config_filename = self._config_filename

        script_path = os.path.abspath(__file__)
        project_root = os.path.abspath(os.path.join(script_path, '..', '..'))
        config_path = os.path.join(project_root, 'config', config_filename)

        with self._config_lock:
            from aiofile import async_open
            async with async_open(config_path, 'w', encoding='utf-8') as f:
                await f.write(yaml.dump(self._config, default_flow_style=False, allow_unicode=True))

    def get_safe_config(self) -> Dict[str, Any]:
        """
        Get a dictionary of the configuration without sensitive information.
        """
        result = {}
        for key in self._config:
            value = getattr(self, key)
            if isinstance(value, ConfigSection):
                result[key] = value.to_dict()
            elif isinstance(value, str) and 'token' in key.lower():
                result[key] = '***REDACTED***'
            else:
                result[key] = value
        return result

    def __getitem__(self, item):
        return self._config.get(item, None)

    def __repr__(self):
        return f"<ConfigManager {self._config_filename}>"