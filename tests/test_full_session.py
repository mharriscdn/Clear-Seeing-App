"""
Full session simulation test.

Simulates a user session progressing from mirror → examinability →
orient → hold_both_forces → gibraltar.
"""

from unittest.mock import patch
from services.chat_service import process_chat


def test_full_session_flow():

    session_id = 1
    user_id = 1

    responses = [
        ("Reflection text\n{\"phase_signal\":\"stay\"}", 100, "claude"),
        ("Examine text\n{\"phase_signal\":\"advance\"}", 100, "claude"),
        ("Orient text\n{\"phase_signal\":\"advance\"}", 100, "claude"),
        ("Hold both\n{\"phase_signal\":\"advance\"}", 100, "claude"),
        ("Release\n{\"phase_signal\":\"path_b\"}", 100, "claude"),
    ]

    user_messages = [
        "Something feels off with my partner.",
        "I keep asking if they are upset.",
        "There is tightness in my chest.",
        "The urge to check keeps coming back.",
        "The pressure softened."
    ]

    with patch("services.chat_service.llm.call_claude") as mock_llm:
        with patch("services.chat_service.db") as mock_db:
            with patch("services.phase_engine.db") as mock_phase_db:

                mock_llm.side_effect = responses

                mock_db.get_session.side_effect = [
                    {"id": 1, "conversation_phase": "mirror", "entry_charge": None, "exit_charge": None},
                    {"id": 1, "conversation_phase": "mirror", "entry_charge": None, "exit_charge": None},
                    {"id": 1, "conversation_phase": "mirror", "entry_charge": None, "exit_charge": None},
                    {"id": 1, "conversation_phase": "mirror", "entry_charge": None, "exit_charge": None},
                    {"id": 1, "conversation_phase": "examinability", "entry_charge": None, "exit_charge": None},
                    {"id": 1, "conversation_phase": "examinability", "entry_charge": None, "exit_charge": None},
                    {"id": 1, "conversation_phase": "activation_check", "entry_charge": None, "exit_charge": None},
                    {"id": 1, "conversation_phase": "activation_check", "entry_charge": None, "exit_charge": None},
                    {"id": 1, "conversation_phase": "hold_both_forces", "entry_charge": None, "exit_charge": None},
                    {"id": 1, "conversation_phase": "hold_both_forces", "entry_charge": None, "exit_charge": None},
                ]
                mock_db.get_session_messages.return_value = []
                mock_db.save_message.return_value = {"id": 1}
                mock_phase_db.increment_evasion_count.return_value = 0

                for message in user_messages:
                    process_chat(session_id, user_id, message)

                mock_phase_db.update_session_phase.assert_called()
