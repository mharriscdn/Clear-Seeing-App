"""
Tests for services/chat_service.py — v9 single-prompt pipeline.

Mocks the LLM and all DB calls so the chat pipeline can be tested
without a real model or database connection.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock, call
from services.chat_service import process_chat


def make_session(phase="session"):
    return {
        "id": 1,
        "user_id": 1,
        "conversation_phase": phase,
        "entry_charge": None,
        "exit_charge": None,
    }


def make_llm_result(text="Claude response."):
    return {
        "content": text,
        "input_tokens": 100,
        "output_tokens": 50,
        "cached_tokens": 80,
        "model": "claude-test",
    }


def test_first_message_sets_phase_and_opening_problem():
    """
    On the very first user message, process_chat must:
    - set the session phase to 'session'
    - set opening_problem in the DB
    - call the capacity gate
    - return the assistant text
    """
    with patch("services.chat_service.db") as mock_db, \
         patch("services.chat_service.llm.call_claude") as mock_llm:

        mock_db.get_session.return_value = make_session()
        mock_db.get_session_messages.side_effect = [
            [],
            [
                {"role": "user",      "content": "I feel like a fraud."},
                {"role": "assistant", "content": "Claude response."},
            ],
        ]
        mock_db.can_start_session.return_value = True
        mock_db.save_message.return_value = {"id": 1}
        mock_db.deduct_capacity.return_value = 5
        mock_llm.return_value = make_llm_result()

        text, transcript = process_chat(
            session_id=1,
            user_id=1,
            user_message="I feel like a fraud.",
        )

        mock_db.update_session_phase.assert_called_once_with(1, "session")
        mock_db.set_opening_problem.assert_called_once_with(1, "I feel like a fraud.")
        mock_db.can_start_session.assert_called_once_with(1)
        assert text == "Claude response."


def test_subsequent_message_skips_first_reply_logic():
    """
    On a follow-up message, process_chat must NOT call can_start_session,
    set_opening_problem, or update_session_phase.
    """
    with patch("services.chat_service.db") as mock_db, \
         patch("services.chat_service.llm.call_claude") as mock_llm:

        existing = [
            {"role": "user",      "content": "First message."},
            {"role": "assistant", "content": "First reply."},
        ]
        mock_db.get_session.return_value = make_session()
        mock_db.get_session_messages.side_effect = [
            existing,
            existing + [
                {"role": "user",      "content": "Follow up."},
                {"role": "assistant", "content": "Second reply."},
            ],
        ]
        mock_db.save_message.return_value = {"id": 2}
        mock_db.deduct_capacity.return_value = 5
        mock_llm.return_value = make_llm_result("Second reply.")

        text, transcript = process_chat(
            session_id=1,
            user_id=1,
            user_message="Follow up.",
        )

        mock_db.can_start_session.assert_not_called()
        mock_db.set_opening_problem.assert_not_called()
        mock_db.update_session_phase.assert_not_called()
        assert text == "Second reply."


def test_capacity_exhausted_raises():
    """
    When can_start_session returns False on the first message,
    process_chat must raise ValueError before calling Claude.
    """
    with patch("services.chat_service.db") as mock_db, \
         patch("services.chat_service.llm.call_claude") as mock_llm:

        mock_db.get_session.return_value = make_session()
        mock_db.get_session_messages.return_value = []
        mock_db.can_start_session.return_value = False

        try:
            process_chat(session_id=1, user_id=1, user_message="Hello.")
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "capacity" in str(e).lower()

        mock_llm.assert_not_called()


def test_invalid_session_raises():
    """
    When get_session returns None, process_chat must raise ValueError.
    """
    with patch("services.chat_service.db") as mock_db:
        mock_db.get_session.return_value = None

        try:
            process_chat(session_id=99, user_id=1, user_message="Hello.")
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "not found" in str(e).lower()


def test_assistant_reply_saved_with_token_data():
    """
    The assistant reply must be saved with full token accounting.
    """
    with patch("services.chat_service.db") as mock_db, \
         patch("services.chat_service.llm.call_claude") as mock_llm:

        existing = [
            {"role": "user",      "content": "Earlier message."},
            {"role": "assistant", "content": "Earlier reply."},
        ]
        mock_db.get_session.return_value = make_session()
        mock_db.get_session_messages.side_effect = [existing, existing]
        mock_db.save_message.return_value = {"id": 3}
        mock_db.deduct_capacity.return_value = 7
        mock_llm.return_value = make_llm_result("Answer.")

        process_chat(session_id=1, user_id=1, user_message="Question.")

        save_calls = mock_db.save_message.call_args_list
        assistant_call = next(
            c for c in save_calls if c.args[1] == "assistant"
        )
        kwargs = assistant_call.kwargs
        assert kwargs["input_tokens"] == 100
        assert kwargs["output_tokens"] == 50
        assert kwargs["cached_tokens"] == 80
        assert kwargs["capacity_units_deducted"] == 7


def test_full_message_history_passed_to_claude():
    """
    Claude must receive the complete conversation history plus the new
    user message — not just the latest turn.
    """
    with patch("services.chat_service.db") as mock_db, \
         patch("services.chat_service.llm.call_claude") as mock_llm:

        existing = [
            {"role": "user",      "content": "Turn 1 user."},
            {"role": "assistant", "content": "Turn 1 assistant."},
        ]
        mock_db.get_session.return_value = make_session()
        mock_db.get_session_messages.side_effect = [existing, existing]
        mock_db.save_message.return_value = {"id": 4}
        mock_db.deduct_capacity.return_value = 5
        mock_llm.return_value = make_llm_result()

        process_chat(session_id=1, user_id=1, user_message="Turn 2 user.")

        passed_messages = mock_llm.call_args.args[0]
        assert len(passed_messages) == 3
        assert passed_messages[0]["content"] == "Turn 1 user."
        assert passed_messages[1]["content"] == "Turn 1 assistant."
        assert passed_messages[2]["content"] == "Turn 2 user."
