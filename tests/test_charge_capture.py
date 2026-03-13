"""
Tests for charge capture logic and charge_delta_summary.

Covers:
  - entry_charge captured after mirror is delivered
  - entry_charge not captured on first message (before mirror)
  - entry_charge not recaptured if already set
  - exit_charge captured during re_examination phase
  - exit_charge NOT captured on path_a exit (recurrence_normalization phase)
  - charge_delta_summary for charge down, charge up, charge unchanged
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, call
from services.chat_service import process_chat, charge_delta_summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_session(phase="mirror", entry_charge=None, exit_charge=None):
    return {
        "id": 1,
        "user_id": 1,
        "conversation_phase": phase,
        "entry_charge": entry_charge,
        "exit_charge": exit_charge,
        "evasion_count": 0,
        "signal_retry": False,
    }


def run_process_chat(session, user_message, prior_messages=None, llm_response=None):
    """Helper: run process_chat with full mocking, return mock_db."""
    if prior_messages is None:
        prior_messages = []
    if llm_response is None:
        llm_response = 'Coach response.\n{"phase_signal": "stay"}'

    with patch("services.chat_service.llm.call_claude") as mock_llm, \
         patch("services.chat_service.db") as mock_db, \
         patch("services.phase_engine.db") as mock_phase_db:

        mock_llm.return_value = {"content": llm_response, "input_tokens": 60, "output_tokens": 40, "cached_tokens": 0, "model": "claude-test"}
        mock_db.get_session.return_value = session
        mock_db.get_session_messages.return_value = prior_messages
        mock_db.save_message.return_value = {"id": 99}
        mock_phase_db.increment_evasion_count.return_value = 0

        process_chat(1, 1, user_message)
        return mock_db


# ---------------------------------------------------------------------------
# Entry charge tests
# ---------------------------------------------------------------------------

def test_entry_charge_captured_after_mirror():
    """
    Mirror phase + at least one prior assistant message + user gives a number
    → update_session_charge called with ('entry_charge', 7).
    """
    session = make_session(phase="mirror", entry_charge=None)
    prior_messages = [
        {"role": "assistant", "content": "Mirror reflection. How charged does that feel, 1 to 10?"},
    ]

    mock_db = run_process_chat(session, "About a 7", prior_messages=prior_messages)

    mock_db.update_session_charge.assert_called_once_with(1, "entry_charge", 7)


def test_entry_charge_not_captured_on_first_message():
    """
    Mirror phase + NO prior assistant messages (user is still telling story)
    → update_session_charge must NOT be called.
    """
    session = make_session(phase="mirror", entry_charge=None)

    mock_db = run_process_chat(session, "I've been stressed about this for 3 weeks.", prior_messages=[])

    for c in mock_db.update_session_charge.call_args_list:
        assert c.args[1] != "entry_charge", "entry_charge must not be captured before mirror is delivered"


def test_entry_charge_not_recaptured_if_already_set():
    """
    Mirror phase + entry_charge already recorded
    → update_session_charge must NOT be called again.
    """
    session = make_session(phase="mirror", entry_charge=6)
    prior_messages = [
        {"role": "assistant", "content": "Mirror reflection. How charged does that feel, 1 to 10?"},
    ]

    mock_db = run_process_chat(session, "Still about a 6.", prior_messages=prior_messages)

    for c in mock_db.update_session_charge.call_args_list:
        assert c.args[1] != "entry_charge", "entry_charge must not be overwritten once set"


# ---------------------------------------------------------------------------
# Exit charge tests
# ---------------------------------------------------------------------------

def test_exit_charge_captured_in_re_examination():
    """
    re_examination phase + at least one prior assistant message + user gives a number
    → update_session_charge called with ('exit_charge', 3).
    """
    session = make_session(phase="re_examination", entry_charge=8, exit_charge=None)
    prior_messages = [
        {"role": "assistant", "content": "You came in with that problem. Look at it now. What do you see?"},
    ]

    mock_db = run_process_chat(session, "About a 3, it feels a lot lighter.", prior_messages=prior_messages)

    mock_db.update_session_charge.assert_called_once_with(1, "exit_charge", 3)


def test_exit_charge_not_captured_in_path_a_exit():
    """
    Path A exit routes to recurrence_normalization — re_examination never runs.
    update_session_charge must NOT be called for exit_charge on this path.
    """
    session = make_session(phase="recurrence_normalization", entry_charge=5, exit_charge=None)
    prior_messages = [
        {"role": "assistant", "content": "Path A close."},
    ]

    mock_db = run_process_chat(session, "Okay, thank you.", prior_messages=prior_messages)

    for c in mock_db.update_session_charge.call_args_list:
        assert c.args[1] != "exit_charge", "exit_charge must not be captured on path_a exit"


# ---------------------------------------------------------------------------
# charge_delta_summary tests
# ---------------------------------------------------------------------------

def test_charge_delta_summary_charge_down():
    """Charge dropped: result must reference both numbers."""
    result = charge_delta_summary(8, 3)
    assert "8" in result
    assert "3" in result


def test_charge_delta_summary_charge_up():
    """Charge rose: result must reference both numbers."""
    result = charge_delta_summary(3, 7)
    assert "3" in result
    assert "7" in result


def test_charge_delta_summary_charge_unchanged():
    """Charge held: result must reference the number."""
    result = charge_delta_summary(5, 5)
    assert "5" in result
