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
                    (responses[0][1], 100, "claude"),
                    (responses[1][1], 100, "claude"),
                    (responses[2][1], 100, "claude"),
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
