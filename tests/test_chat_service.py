"""
Integration tests for services/chat_service.py

Mocks the LLM response and all DB calls so the full chat pipeline
can be tested without a real model or database connection.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock
from services.chat_service import process_chat


def make_session(phase="mirror"):
    return {
        "id": 1,
        "user_id": 1,
        "conversation_phase": phase,
        "entry_charge": None,
        "exit_charge": None,
        "evasion_count": 0,
    }


def test_chat_advance_signal():
    """
    When the LLM returns {"phase_signal": "advance"} from mirror phase,
    the phase engine must advance the session to examinability.
    """
    mock_llm_response = """
    Let's examine what happens when the reassurance question appears.

    {"phase_signal": "advance"}
    """

    with patch("services.chat_service.llm.call_claude") as mock_llm, \
         patch("services.chat_service.db") as mock_db, \
         patch("services.phase_engine.db") as mock_phase_db:

        mock_llm.return_value = {"content": mock_llm_response, "input_tokens": 100, "output_tokens": 50, "cached_tokens": 0, "model": "claude-test"}

        mock_db.get_session.return_value = make_session(phase="mirror")
        mock_db.get_session_messages.return_value = []
        mock_db.save_message.return_value = {"id": 1}

        mock_phase_db.increment_evasion_count.return_value = 0

        assistant_text, transcript = process_chat(
            session_id=1,
            user_id=1,
            user_message="I keep asking my partner if everything is okay.",
        )

        mock_phase_db.update_session_phase.assert_called_once_with(1, "contact")
        # Phase signal JSON must be stripped from the returned text before display
        assert '{"phase_signal"' not in assistant_text
        assert "Let's examine what happens when the reassurance question appears." in assistant_text
