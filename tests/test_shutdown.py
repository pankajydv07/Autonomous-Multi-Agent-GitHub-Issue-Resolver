import pytest
import asyncio
from unittest.mock import MagicMock
from orchestrator.worker import shutdown_event, signal_handler

def test_shutdown_signal_handler_sets_event():
    # Reset event state
    shutdown_event.clear()
    assert shutdown_event.is_set() is False
    
    # Trigger signal handler
    signal_handler(MagicMock(), MagicMock())
    
    # Assert that the shutdown event is now set
    assert shutdown_event.is_set() is True
