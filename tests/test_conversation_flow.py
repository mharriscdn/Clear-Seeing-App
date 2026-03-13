"""
Conversation flow simulation tests.

These tests simulate a multi-turn conversation using mocked LLM responses.
They verify that the conversation phase progresses correctly across turns.
"""

from unittest.mock import patch
from services.chat_service import process_chat


def make_session():
    return {
        "id": 1,
        "conversation_phase": "mirror",
        "entry_charge": None,
        "exit_charge": None,
    }


def test_basic_conversation_flow():

    session = make_session()

    responses = [
        # Turn 1 – stay in mirror
        ("I'm anxious my partner is upset with me.",
         'Reflection text\n{"phase_signal": "stay"}'),

        # Turn 2 – advance to examinability
        ("I keep asking if everything is okay.",
         'Coaching text\n{"phase_signal": "advance"}'),

        # Turn 3 – advance again
        ("There's a tight feeling in my chest.",
         'Coaching text\n{"phase_signal": "advance"}'),
    ]

    with patch("services.chat_service.llm.call_claude") as mock_llm:
        with patch("services.chat_service.db") as mock_db:
            with patch("services.phase_engine.db") as mock_phase_db:

                mock_llm.side_effect = [
                    {"content": responses[0][1], "input_tokens": 60, "output_tokens": 40, "cached_tokens": 0, "model": "claude"},
                    {"content": responses[1][1], "input_tokens": 60, "output_tokens": 40, "cached_tokens": 0, "model": "claude"},
                    {"content": responses[2][1], "input_tokens": 60, "output_tokens": 40, "cached_tokens": 0, "model": "claude"},
                ]

                mock_db.get_session.return_value = make_session()
                mock_db.get_session_messages.return_value = []
                mock_db.save_message.return_value = {"id": 1}
                mock_phase_db.increment_evasion_count.return_value = 0

                process_chat(1, 1, responses[0][0])
                process_chat(1, 1, responses[1][0])
                process_chat(1, 1, responses[2][0])

                # Verify the phase progressed
                assert mock_phase_db.update_session_phase.call_count >= 1


def test_evasion_exit_after_three_stays():

    responses = [
        ('Text\n{"phase_signal": "stay"}'),
        ('Text\n{"phase_signal": "stay"}'),
        ('Text\n{"phase_signal": "stay"}'),
    ]

    with patch("services.chat_service.llm.call_claude") as mock_llm:
        with patch("services.chat_service.db") as mock_db:
            with patch("services.phase_engine.db") as mock_phase_db:

                # Must be an evasion phase — "mirror" is not in EVASION_PHASES
                evasion_session = make_session()
                evasion_session["conversation_phase"] = "orient"
                mock_db.get_session.return_value = evasion_session
                mock_db.get_session_messages.return_value = []
                mock_db.save_message.return_value = {"id": 1}

                mock_phase_db.increment_evasion_count.side_effect = [1, 2, 3]

                mock_llm.side_effect = [
                    {"content": responses[0], "input_tokens": 60, "output_tokens": 40, "cached_tokens": 0, "model": "claude"},
                    {"content": responses[1], "input_tokens": 60, "output_tokens": 40, "cached_tokens": 0, "model": "claude"},
                    {"content": responses[2], "input_tokens": 60, "output_tokens": 40, "cached_tokens": 0, "model": "claude"},
                ]

                process_chat(1, 1, "message 1")
                process_chat(1, 1, "message 2")
                process_chat(1, 1, "message 3")

                mock_phase_db.update_session_phase.assert_called_with(
                    1, "recurrence_normalization"
                )


def test_hold_both_forces_path_b_routes_to_gibraltar():

    response = 'Text\n{"phase_signal": "path_b"}'

    with patch("services.chat_service.llm.call_claude") as mock_llm:
        with patch("services.chat_service.db") as mock_db:
            with patch("services.phase_engine.db") as mock_phase_db:

                fork_session = make_session()
                fork_session["conversation_phase"] = "hold_both_forces"
                fork_session["entry_charge"] = 8
                fork_session["exit_charge"] = 5
                mock_db.get_session.return_value = fork_session
                mock_db.get_session_messages.return_value = []
                mock_db.save_message.return_value = {"id": 1}
                mock_phase_db.increment_evasion_count.return_value = 0

                mock_llm.return_value = {"content": response, "input_tokens": 60, "output_tokens": 40, "cached_tokens": 0, "model": "claude"}

                process_chat(1, 1, "message")

                mock_phase_db.update_session_phase.assert_called_with(
                    1, "gibraltar"
                )


def test_hold_both_forces_path_a_routes_to_recurrence():

    response = 'Text\n{"phase_signal": "path_a"}'

    with patch("services.chat_service.llm.call_claude") as mock_llm:
        with patch("services.chat_service.db") as mock_db:
            with patch("services.phase_engine.db") as mock_phase_db:

                fork_session = make_session()
                fork_session["conversation_phase"] = "hold_both_forces"
                fork_session["entry_charge"] = 5
                fork_session["exit_charge"] = 4
                mock_db.get_session.return_value = fork_session
                mock_db.get_session_messages.return_value = []
                mock_db.save_message.return_value = {"id": 1}
                mock_phase_db.increment_evasion_count.return_value = 0

                mock_llm.return_value = {"content": response, "input_tokens": 60, "output_tokens": 40, "cached_tokens": 0, "model": "claude"}

                process_chat(1, 1, "message")

                mock_phase_db.update_session_phase.assert_called_with(
                    1, "recurrence_normalization"
                )


def test_missing_signal_defaults_to_stay():

    response = "LLM forgot to include a signal"

    with patch("services.chat_service.llm.call_claude") as mock_llm:
        with patch("services.chat_service.db") as mock_db:
            with patch("services.phase_engine.db") as mock_phase_db:

                mock_db.get_session.return_value = make_session()
                mock_db.get_session_messages.return_value = []
                mock_db.save_message.return_value = {"id": 1}
                mock_phase_db.increment_evasion_count.return_value = 0

                mock_llm.return_value = {"content": response, "input_tokens": 60, "output_tokens": 40, "cached_tokens": 0, "model": "claude"}

                process_chat(1, 1, "message")

                mock_phase_db.update_session_phase.assert_not_called()
