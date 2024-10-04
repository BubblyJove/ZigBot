import sys
import os
import asyncio
import threading
import time
import logging
import psutil  # Added for extended resource monitoring

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QWidget, QTextEdit, QLineEdit, QLabel, QFileDialog, QInputDialog, QGroupBox,
    QScrollArea, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer
from PyQt5.QtGui import QPixmap, QPainter, QTextCharFormat, QColor

try:
    from PyQt5.QtChart import QChart, QChartView, QLineSeries, QValueAxis
except ImportError:
    print("PyQt5.QtChart is not available. Some features may be disabled.")
    QChart = QChartView = QLineSeries = QValueAxis = None

# Ensure the bot package directory is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
bot_dir = os.path.abspath(os.path.join(current_dir, '..'))
if bot_dir not in sys.path:
    sys.path.insert(0, bot_dir)

from main import DiscordBot
from utils.config_manager import ConfigManager

class BotThread(threading.Thread):
    class LogSignal(QObject):
        signal = pyqtSignal(str, str)  # Added log level

    class StatusSignal(QObject):
        signal = pyqtSignal(str)

    class MetricsSignal(QObject):
        signal = pyqtSignal(float, float, float, float, float, dict)  # Added new metrics

    def __init__(self):
        super().__init__()
        self.config = ConfigManager('bot_config.yaml')
        self.token = self.config.discord.token
        self.prefix = self.config.discord.get('prefix', '!')
        self.admin_channel_id = self.config.bot.get('admin_channel_id', None)
        self.loop = None
        self.bot = None
        self.log_signal = self.LogSignal()
        self.status_signal = self.StatusSignal()
        self.metrics_signal = self.MetricsSignal()
        self._stop_event = threading.Event()
        self.daemon = True  # Ensure the thread exits when the main program does

    def run(self):
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.bot = DiscordBot(status_callback=self.on_status_update)
            self.bot.bot.command_prefix = self.prefix
            # Update config with admin_channel_id
            self.bot.config.bot.set('admin_channel_id', self.admin_channel_id)
            # Update config with token
            self.bot.config.discord.set('token', self.token)
            # Connect bot's logger to the control panel's log signal
            self.bot.bot.logger = self.BotLogger(self.log_signal.signal)

            # Adjust logging levels to prevent Unicode errors
            logging.getLogger('discord').setLevel(logging.INFO)
            logging.getLogger('discord.http').setLevel(logging.WARNING)
            logging.getLogger('asyncio').setLevel(logging.WARNING)

            self.status_signal.signal.emit("Starting")
            self.log_signal.signal.emit("Starting bot...", "INFO")

            # Debug: Check if the token has been loaded correctly
            if self.token and len(self.token) >= 59:
                self.bot.bot.logger.info(f"Discord Token Loaded: {'*' * 10}{self.token[-4:]} (Length: {len(self.token)})")
            else:
                self.bot.bot.logger.error("Discord Token is missing or invalid in the configuration.")

            self.loop.run_until_complete(self.start_bot())
        except Exception as e:
            self.log_signal.signal.emit(f"Bot encountered an error: {e}", "ERROR")
            self.status_signal.signal.emit("Error")
            import traceback
            traceback.print_exc()
        finally:
            if self.bot and not self.bot.bot.is_closed():
                self.loop.run_until_complete(self.bot.stop())
            self.loop.close()
            self.status_signal.signal.emit("Offline")
            self.log_signal.signal.emit("Bot has been stopped.", "INFO")

    async def start_bot(self):
        await self.bot.start(self.token)

    def stop(self):
        if self.bot and not self.bot.bot.is_closed():
            self.status_signal.signal.emit("Stopping")
            self.log_signal.signal.emit("Stopping bot...", "WARNING")
            asyncio.run_coroutine_threadsafe(self.bot.stop(), self.loop)
            self._stop_event.set()

    def on_status_update(self, status):
        self.status_signal.signal.emit(status)

    def collect_metrics(self):
        """
        Collect metrics and emit them via the metrics_signal.
        """
        while not self._stop_event.is_set():
            if self.bot:
                uptime = self.bot.get_uptime()
                memory = self.bot.get_memory_usage()
                cpu = self.bot.get_cpu_usage()

                # Extended metrics
                disk_io = self.bot.get_disk_io_usage()
                network = self.bot.get_network_usage()
                thread_performance = self.bot.get_thread_performance()

                self.metrics_signal.signal.emit(uptime, memory, cpu, disk_io, network, thread_performance)
            time.sleep(5)  # Collect metrics every 5 seconds

    class BotLogger:
        def __init__(self, log_signal):
            self.log_signal = log_signal
            self.logger = logging.getLogger('bot_logger')
            # Ensure the logger has handlers
            if not self.logger.handlers:
                handler = logging.FileHandler('bot_control_panel.log', encoding='utf-8')
                handler.setFormatter(
                    logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                )
                self.logger.addHandler(handler)
                self.logger.setLevel(logging.DEBUG)

        def info(self, message, *args, **kwargs):
            self.log_signal.emit(message, "INFO")
            self.logger.info(message, *args, **kwargs)

        def warning(self, message, *args, **kwargs):
            self.log_signal.emit(message, "WARNING")
            self.logger.warning(message, *args, **kwargs)

        def error(self, message, *args, **kwargs):
            self.log_signal.emit(message, "ERROR")
            self.logger.error(message, *args, **kwargs)

        def critical(self, message, *args, **kwargs):
            self.log_signal.emit(message, "CRITICAL")
            self.logger.critical(message, *args, **kwargs)

class ControlPanel(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Discord Bot Control Panel")
        self.setGeometry(100, 100, 1200, 800)
        self.setStyleSheet(self.get_stylesheet())

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)

        # Initialize attributes
        self.bot_thread = None
        self.token_input = None
        self.prefix_input = None
        self.admin_channel_input = None
        self.status_label = None
        self.log_display = None
        self.uptime_label = None
        self.memory_label = None
        self.cpu_label = None
        self.disk_io_label = None  # New label for disk I/O
        self.network_label = None  # New label for network usage
        self.cpu_series = None
        self.memory_series = None
        self.disk_io_series = None  # New series for disk I/O
        self.network_series = None  # New series for network usage
        self.data_counter = 0
        self.active_cogs_plugins = None
        self.plugin_list = None

        # Initialize UI components before loading config
        self.create_sidebar()
        self.create_main_area()
        self.load_config()  # Ensure UI elements are initialized before calling this

    def get_stylesheet(self):
        # Stylesheet code with color-coded logs
        return """
        QMainWindow, QWidget {
            background-color: #2C2F33;
            color: #FFFFFF;
        }
        QPushButton {
            background-color: #7289DA;
            border: none;
            border-radius: 5px;
            padding: 10px;
            margin: 5px;
            color: #FFFFFF;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #677BC4;
        }
        QPushButton:pressed {
            background-color: #5B6EAE;
        }
        QTabWidget::pane {
            border: 1px solid #23272A;
            background-color: #2C2F33;
        }
        QTabBar::tab {
            background-color: #23272A;
            color: #FFFFFF;
            padding: 10px;
            margin: 2px;
        }
        QTabBar::tab:selected {
            background-color: #7289DA;
        }
        QTextEdit, QLineEdit {
            background-color: #23272A;
            color: #FFFFFF;
            border: 1px solid #7289DA;
            border-radius: 5px;
            padding: 5px;
        }
        QGroupBox {
            border: 2px solid #7289DA;
            border-radius: 5px;
            margin-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 3px 0 3px;
        }
        QLabel {
            color: #FFFFFF;
        }
        """

    def create_sidebar(self):
        # Sidebar creation code
        sidebar = QWidget()
        sidebar.setFixedWidth(200)
        sidebar_layout = QVBoxLayout(sidebar)

        logo_label = QLabel()
        logo_pixmap = QPixmap("assets/logo.png")  # Replace with your logo path
        if not logo_pixmap.isNull():
            logo_label.setPixmap(logo_pixmap.scaled(180, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            sidebar_layout.addWidget(logo_label, alignment=Qt.AlignCenter)
        else:
            logo_label.setText("No Logo")
            sidebar_layout.addWidget(logo_label, alignment=Qt.AlignCenter)

        self.status_label = QLabel("Status: Offline")
        self.status_label.setStyleSheet("font-weight: bold; color: #FF6B6B;")
        sidebar_layout.addWidget(self.status_label)

        control_group = QGroupBox("Bot Control")
        control_layout = QVBoxLayout(control_group)
        self.start_button = QPushButton("Start Bot")
        self.stop_button = QPushButton("Stop Bot")
        self.restart_button = QPushButton("Restart Bot")
        self.start_button.clicked.connect(self.start_bot)
        self.stop_button.clicked.connect(self.stop_bot)
        self.restart_button.clicked.connect(self.restart_bot)
        control_layout.addWidget(self.start_button)
        control_layout.addWidget(self.stop_button)
        control_layout.addWidget(self.restart_button)
        sidebar_layout.addWidget(control_group)

        sidebar_layout.addStretch()

        self.main_layout.addWidget(sidebar)

    def create_main_area(self):
        self.main_area = QTabWidget()
        self.main_area.addTab(self.create_dashboard_tab(), "Dashboard")
        self.main_area.addTab(self.create_logs_tab(), "Logs")
        self.main_area.addTab(self.create_config_tab(), "Configuration")
        self.main_area.addTab(self.create_plugin_tab(), "Plugins")
        self.main_layout.addWidget(self.main_area)

    def create_dashboard_tab(self):
        dashboard = QWidget()
        layout = QVBoxLayout(dashboard)

        metrics_group = QGroupBox("Bot Metrics")
        metrics_layout = QHBoxLayout(metrics_group)
        self.uptime_label = QLabel("Uptime: N/A")
        self.memory_label = QLabel("Memory Usage: N/A")
        self.cpu_label = QLabel("CPU Usage: N/A")
        self.disk_io_label = QLabel("Disk I/O: N/A")
        self.network_label = QLabel("Network Usage: N/A")
        metrics_layout.addWidget(self.uptime_label)
        metrics_layout.addWidget(self.memory_label)
        metrics_layout.addWidget(self.cpu_label)
        metrics_layout.addWidget(self.disk_io_label)
        metrics_layout.addWidget(self.network_label)
        layout.addWidget(metrics_group)

        if QChart is not None:
            self.chart = QChart()
            self.chart.setTitle("Resource Usage Over Time")
            self.cpu_series = QLineSeries(name="CPU Usage (%)")
            self.memory_series = QLineSeries(name="Memory Usage (MB)")
            self.disk_io_series = QLineSeries(name="Disk I/O (Bytes)")
            self.network_series = QLineSeries(name="Network Usage (Bytes)")
            self.chart.addSeries(self.cpu_series)
            self.chart.addSeries(self.memory_series)
            self.chart.addSeries(self.disk_io_series)
            self.chart.addSeries(self.network_series)

            axis_x = QValueAxis()
            axis_x.setLabelFormat("%d")
            axis_x.setTitleText("Time (s)")
            self.chart.addAxis(axis_x, Qt.AlignBottom)
            self.cpu_series.attachAxis(axis_x)
            self.memory_series.attachAxis(axis_x)
            self.disk_io_series.attachAxis(axis_x)
            self.network_series.attachAxis(axis_x)

            axis_y = QValueAxis()
            axis_y.setLabelFormat("%.1f")
            axis_y.setTitleText("Usage")
            self.chart.addAxis(axis_y, Qt.AlignLeft)
            self.cpu_series.attachAxis(axis_y)
            self.memory_series.attachAxis(axis_y)
            self.disk_io_series.attachAxis(axis_y)
            self.network_series.attachAxis(axis_y)

            chart_view = QChartView(self.chart)
            chart_view.setRenderHint(QPainter.Antialiasing)
            layout.addWidget(chart_view)

            self.data_counter = 0
        else:
            layout.addWidget(QLabel("Charts are not available. Install PyQtChart for this feature."))

        # Active cogs and plugins
        active_group = QGroupBox("Active Cogs and Plugins")
        active_layout = QVBoxLayout(active_group)
        self.active_cogs_plugins = QTextEdit()
        self.active_cogs_plugins.setReadOnly(True)
        active_layout.addWidget(self.active_cogs_plugins)
        layout.addWidget(active_group)

        return dashboard

    def create_logs_tab(self):
        logs_tab = QWidget()
        layout = QVBoxLayout(logs_tab)

        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        layout.addWidget(self.log_display)

        clear_logs_button = QPushButton("Clear Logs")
        clear_logs_button.clicked.connect(self.clear_logs)
        layout.addWidget(clear_logs_button)

        return logs_tab

    def create_config_tab(self):
        config_tab = QScrollArea()
        config_tab.setWidgetResizable(True)
        config_widget = QWidget()
        layout = QVBoxLayout(config_widget)

        token_group = QGroupBox("Discord Token")
        token_layout = QHBoxLayout(token_group)
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.Password)
        token_layout.addWidget(QLabel("Token:"))
        token_layout.addWidget(self.token_input)
        layout.addWidget(token_group)

        prefix_group = QGroupBox("Command Prefix")
        prefix_layout = QHBoxLayout(prefix_group)
        self.prefix_input = QLineEdit()
        prefix_layout.addWidget(QLabel("Prefix:"))
        prefix_layout.addWidget(self.prefix_input)
        layout.addWidget(prefix_group)

        admin_channel_group = QGroupBox("Admin Channel ID")
        admin_channel_layout = QHBoxLayout(admin_channel_group)
        self.admin_channel_input = QLineEdit()
        admin_channel_layout.addWidget(QLabel("Channel ID:"))
        admin_channel_layout.addWidget(self.admin_channel_input)
        layout.addWidget(admin_channel_group)

        save_button = QPushButton("Save Configuration")
        save_button.clicked.connect(self.save_config)
        layout.addWidget(save_button)

        layout.addStretch()
        config_tab.setWidget(config_widget)
        return config_tab

    def create_plugin_tab(self):
        plugin_tab = QWidget()
        layout = QVBoxLayout(plugin_tab)

        self.plugin_list = QTextEdit()
        self.plugin_list.setReadOnly(True)
        layout.addWidget(self.plugin_list)

        button_layout = QHBoxLayout()
        refresh_button = QPushButton("Refresh Plugin List")
        load_button = QPushButton("Load Plugin")
        unload_button = QPushButton("Unload Plugin")
        refresh_button.clicked.connect(self.refresh_plugins)
        load_button.clicked.connect(self.load_plugin)
        unload_button.clicked.connect(self.unload_plugin)
        button_layout.addWidget(refresh_button)
        button_layout.addWidget(load_button)
        button_layout.addWidget(unload_button)
        layout.addLayout(button_layout)

        return plugin_tab

    def start_bot(self):
        if self.bot_thread is None or not self.bot_thread.is_alive():
            config_manager = ConfigManager('bot_config.yaml')
            token = config_manager.discord.token
            prefix = config_manager.discord.get('prefix', '!')
            admin_channel_id = config_manager.bot.get('admin_channel_id', None)
            if not token or token.strip() == "" or token.strip() == "${DISCORD_TOKEN}":
                self.update_log("Error: No Discord token provided or token is improperly set. Please enter it in the Configuration tab.", "ERROR")
                return
            self.bot_thread = BotThread()
            # Connect signals to slots
            self.bot_thread.log_signal.signal.connect(self.update_log)
            self.bot_thread.status_signal.signal.connect(self.update_status)
            self.bot_thread.metrics_signal.signal.connect(self.update_metrics)
            # Start the bot thread
            self.bot_thread.start()
            # Start metrics collection in a separate thread
            threading.Thread(target=self.bot_thread.collect_metrics, daemon=True).start()
        else:
            QMessageBox.warning(self, "Bot Already Running", "The bot is already running.")

    def stop_bot(self):
        if self.bot_thread and self.bot_thread.is_alive():
            self.bot_thread.stop()
            self.bot_thread.join()
            self.bot_thread = None
            self.update_status("Offline")
        else:
            QMessageBox.warning(self, "Bot Not Running", "The bot is not currently running.")

    def restart_bot(self):
        self.stop_bot()
        self.start_bot()

    def update_log(self, message, level="INFO"):
        color = {
            "INFO": "#FFFFFF",  # White
            "WARNING": "#FFA500",  # Orange
            "ERROR": "#FF0000",  # Red
            "CRITICAL": "#FF69B4",  # Pink
        }.get(level, "#FFFFFF")

        log_entry = f"[{level}] {message}"
        self.log_display.setTextColor(QColor(color))
        self.log_display.append(log_entry)

        # Pop-up for critical events
        if level in ("ERROR", "CRITICAL"):
            QMessageBox.critical(self, "Critical Event", message)

        # Persistent log
        with open('control_panel.log', 'a', encoding='utf-8') as f:
            f.write(f"{log_entry}\n")

    def update_status(self, status):
        self.status_label.setText(f"Status: {status}")
        if status == "Online":
            self.status_label.setStyleSheet("font-weight: bold; color: #43B581;")
            self.update_active_cogs_plugins()
            self.update_log("Bot is now online.", "INFO")
        elif status == "Offline":
            self.status_label.setStyleSheet("font-weight: bold; color: #FF6B6B;")
            self.update_log("Bot is now offline.", "WARNING")
        elif status == "Error":
            self.status_label.setStyleSheet("font-weight: bold; color: #FF6B6B;")
            self.update_log("Bot encountered an error.", "ERROR")
        else:
            self.status_label.setStyleSheet("font-weight: bold; color: #FAA61A;")
            self.update_log(f"Bot status changed: {status}", "WARNING")

    def clear_logs(self):
        self.log_display.clear()
        open('control_panel.log', 'w').close()  # Clear the persistent log file

    def load_config(self):
        try:
            config_manager = ConfigManager('bot_config.yaml')
            self.token_input.setText(config_manager.discord.token)
            self.prefix_input.setText(config_manager.discord.get('prefix', '!'))
            self.admin_channel_input.setText(config_manager.bot.get('admin_channel_id', ''))
        except Exception as e:
            self.update_log(f"Failed to load configuration: {e}", "ERROR")

    def save_config(self):
        try:
            config_manager = ConfigManager('bot_config.yaml')
            config_manager.discord.set('token', self.token_input.text())
            config_manager.discord.set('prefix', self.prefix_input.text())
            config_manager.bot.set('admin_channel_id', self.admin_channel_input.text())
            asyncio.run(config_manager.save())
            self.update_log("Configuration saved successfully.", "INFO")
        except Exception as e:
            self.update_log(f"Error saving configuration: {e}", "ERROR")

    def refresh_plugins(self):
        if self.bot_thread and self.bot_thread.is_alive():
            plugins = self.bot_thread.bot.plugin_manager.list_plugins()
            plugin_statuses = [f"{name}: {status}" for name, status in plugins.items()]
            self.plugin_list.setText("\n".join(plugin_statuses))
            self.update_log("Plugin list refreshed.", "INFO")
        else:
            self.update_log("Bot is not running. Cannot refresh plugins.", "WARNING")

    def load_plugin(self):
        if self.bot_thread and self.bot_thread.is_alive():
            plugin_path, _ = QFileDialog.getOpenFileName(self, "Select Plugin", "", "Python Files (*.py)")
            if plugin_path:
                plugin_name = os.path.basename(plugin_path)[:-3]
                try:
                    asyncio.run_coroutine_threadsafe(
                        self.bot_thread.bot.plugin_manager.load_plugin(plugin_name),
                        self.bot_thread.loop
                    ).result()
                    self.update_log(f"Plugin loaded: {plugin_name}", "INFO")
                    self.refresh_plugins()
                except Exception as e:
                    self.update_log(f"Error loading plugin: {e}", "ERROR")
        else:
            self.update_log("Bot is not running. Cannot load plugin.", "WARNING")

    def unload_plugin(self):
        if self.bot_thread and self.bot_thread.is_alive():
            plugin_name, ok = QInputDialog.getText(self, "Unload Plugin", "Enter plugin name:")
            if ok and plugin_name:
                try:
                    asyncio.run_coroutine_threadsafe(
                        self.bot_thread.bot.plugin_manager.unload_plugin(plugin_name),
                        self.bot_thread.loop
                    ).result()
                    self.update_log(f"Plugin unloaded: {plugin_name}", "INFO")
                    self.refresh_plugins()
                except Exception as e:
                    self.update_log(f"Error unloading plugin: {e}", "ERROR")
        else:
            self.update_log("Bot is not running. Cannot unload plugin.", "WARNING")

    def update_metrics(self, uptime, memory, cpu, disk_io, network, thread_performance):
        self.uptime_label.setText(f"Uptime: {uptime:.2f} seconds")
        self.memory_label.setText(f"Memory Usage: {memory:.2f} MB")
        self.cpu_label.setText(f"CPU Usage: {cpu:.2f}%")
        self.disk_io_label.setText(f"Disk I/O: {disk_io:.2f} Bytes/s")
        self.network_label.setText(f"Network Usage: {network:.2f} Bytes/s")
        self.update_log(f"Updated metrics. CPU: {cpu:.2f}%, Memory: {memory:.2f} MB", "INFO")

        if QChart is not None:
            self.cpu_series.append(self.data_counter, cpu)
            self.memory_series.append(self.data_counter, memory)
            self.disk_io_series.append(self.data_counter, disk_io)
            self.network_series.append(self.data_counter, network)
            self.data_counter += 5  # Assuming update every 5 seconds
            if self.cpu_series.count() > 50:
                self.cpu_series.removePoints(0, self.cpu_series.count() - 50)
                self.memory_series.removePoints(0, self.memory_series.count() - 50)
                self.disk_io_series.removePoints(0, self.disk_io_series.count() - 50)
                self.network_series.removePoints(0, self.network_series.count() - 50)

    def update_active_cogs_plugins(self):
        """Update the list of active cogs and plugins."""
        if self.bot_thread and self.bot_thread.is_alive():
            cogs = list(self.bot_thread.bot.bot.cogs.keys())
            plugins = list(self.bot_thread.bot.plugin_manager.plugins.keys())
            text = f"Active Cogs:\n{', '.join(cogs)}\n\nActive Plugins:\n{', '.join(plugins)}"
            self.active_cogs_plugins.setText(text)
            self.update_log("Updated active cogs and plugins.", "INFO")

if __name__ == "__main__":
    try:
        # Set PYTHONIOENCODING to handle Unicode characters in console output
        os.environ['PYTHONIOENCODING'] = 'utf-8'
        app = QApplication(sys.argv)
        panel = ControlPanel()
        panel.show()
        sys.exit(app.exec_())
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)