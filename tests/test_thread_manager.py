"""
Unit tests for the ThreadManagement cog.

This module contains pytest-based unit tests for the ThreadManagement cog.
It tests various functionalities including fetching catalogs, processing channels,
and handling errors.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from bot.cogs.thread_management import ThreadManagement
from bot.utils.config_manager import ConfigManager
from bot.utils.custom_exceptions import ThreadManagementError

@pytest.fixture
def thread_management():
    """
    Fixture to create a ThreadManagement instance for testing.

    Returns:
        ThreadManagement: An instance of the ThreadManagement cog.
    """
    config = ConfigManager('config/bot_config.yaml')
    return ThreadManagement(Mock(), config)

@pytest.mark.asyncio
async def test_fetch_catalog_success(thread_management):
    """
    Test successful catalog fetching.

    This test mocks a successful API call and checks if the result is correct.
    """
    mock_session = AsyncMock()
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {'threads': [{'no': 1, 'com': 'Test thread'}]}
    mock_session.get.return_value.__aenter__.return_value = mock_response

    result = await thread_management.fetch_catalog(mock_session, 'test_board')

    assert result == {'threads': [{'no': 1, 'com': 'Test thread'}]}
    mock_session.get.assert_called_once_with('https://a.4cdn.org/test_board/catalog.json')

@pytest.mark.asyncio
async def test_fetch_catalog_error(thread_management):
    """
    Test catalog fetching with an error.

    This test mocks a failed API call and checks if the correct exception is raised.
    """
    mock_session = AsyncMock()
    mock_response = AsyncMock()
    mock_response.status = 404
    mock_session.get.return_value.__aenter__.return_value = mock_response

    with pytest.raises(ThreadManagementError):
        await thread_management.fetch_catalog(mock_session, 'test_board')

@pytest.mark.asyncio
async def test_process_channels(thread_management):
    """
    Test processing of multiple channels.

    This test mocks the process_channel method and checks if it's called
    for each channel in the configuration.
    """
    thread_management.config.channels = {
        'channel1': {'data': 'test1'},
        'channel2': {'data': 'test2'}
    }
    thread_management.process_channel = AsyncMock()

    await thread_management.process_channels()

    assert thread_management.process_channel.call_count == 2
    thread_management.process_channel.assert_any_call('channel1', {'data': 'test1'})
    thread_management.process_channel.assert_any_call('channel2', {'data': 'test2'})

@pytest.mark.asyncio
async def test_manual_thread_check_success(thread_management):
    """
    Test the manual thread check command when successful.

    This test mocks the process_channels method and checks if the correct
    success message is sent.
    """
    ctx = AsyncMock()
    thread_management.process_channels = AsyncMock()

    await thread_management.manual_thread_check(ctx)

    thread_management.process_channels.assert_called_once()
    ctx.send.assert_called_once_with("Manual thread check completed successfully.")

@pytest.mark.asyncio
async def test_manual_thread_check_error(thread_management):
    """
    Test the manual thread check command when an error occurs.

    This test mocks the process_channels method to raise an exception and
    checks if the correct error message is sent.
    """
    ctx = AsyncMock()
    thread_management.process_channels = AsyncMock(side_effect=ThreadManagementError("Test error"))

    await thread_management.manual_thread_check(ctx)

    thread_management.process_channels.assert_called_once()
    ctx.send.assert_called_once_with("Thread check failed: Test error")

# Additional tests can be added here for other methods in the ThreadManagement cog