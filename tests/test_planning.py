"""Unit tests for MiMo task planner."""

import pytest
import json
from unittest.mock import MagicMock, patch
import sys
sys.path.insert(0, "../src")

from mimo_client import MiMoClient, TokenUsage, MiMoResponse


def test_mimo_client_init():
    """Client should initialize with default values."""
    client = MiMoClient(api_key="test-key", base_url="http://test/v1")
    assert client.api_key == "test-key"
    assert client.base_url == "http://test/v1"
    assert client.model == "MiMo-V2.5-Pro"


def test_token_tracker_db():
    """Token tracker SQLite DB should initialize correctly."""
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")
        client = MiMoClient(api_key="x", db_path=db)
        client._log_usage("test", TokenUsage(100, 50, 150, 1234.5), "test prompt")
        summary = client.get_usage_summary()
        assert "test" in summary
        assert summary["test"]["total_tokens"] == 150
        assert summary["test"]["calls"] == 1


def test_plan_tasks_prompt():
    """plan_tasks should construct proper system+user prompt."""
    client = MiMoClient(api_key="x")
    tasks = {
        "tasks": [
            {"type": "mint", "amount": 100, "product": "usdc"},
            {"type": "stake", "amount": 50, "product": "cplus"},
        ]
    }

    with patch.object(client, "chat") as mock_chat:
        mock_chat.return_value = MiMoResponse(content="1. Mint USDC\n2. Stake C+")
        result = client.plan_tasks(tasks)

    assert mock_chat.called
    call_args = mock_chat.call_args
    messages = call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert "testnet task executor" in messages[0]["content"].lower()
    assert "mint" in messages[1]["content"]


def test_diagnose_error_prompt():
    """diagnose_error should ask for root cause analysis."""
    client = MiMoClient(api_key="x")

    with patch.object(client, "chat") as mock_chat:
        mock_chat.return_value = MiMoResponse(content="Insufficient gas")
        result = client.diagnose_error("out of gas", "tx context here")

    call_args = mock_chat.call_args
    messages = call_args.kwargs["messages"]
    assert "blockchain transaction debugger" in messages[0]["content"].lower()
    assert "out of gas" in messages[1]["content"]
    assert "root cause" in messages[1]["content"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
