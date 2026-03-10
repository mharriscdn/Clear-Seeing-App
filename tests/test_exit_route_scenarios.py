"""
Exit route scenario tests.

Each test simulates a multi-turn conversation and verifies the final
phase transition. The session is at hold_both_forces on the last turn
so path_a / path_b / path_c signals route correctly.

process_chat calls db.get_session twice per turn (once at entry, once
before the phase engine). side_effect is used to feed the right phase
on each call.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch
from services.chat_service import process_chat


def make_session():
    return {
        "id": 1,
        "conversation_phase": "mirror",
        "entry_charge": None,
        "exit_charge": None,
    }


def make_fork_session():
    s = make_session()
    s["conversation_phase"] = "hold_both_forces"
    return s


def build_db_side_effect(num_turns):
    """
    Returns a side_effect list for db.get_session.
    All turns except the last return mirror phase.
    The last turn returns hold_both_forces so path signals route correctly.
    2 calls per turn: once at session load, once before the phase engine.
    """
    pre_turns = [make_session()] * ((num_turns - 1) * 2)
    last_turn = [make_fork_session(), make_fork_session()]
    return pre_turns + last_turn


def run_turns(mock_llm, mock_db, mock_phase_db, user_messages, llm_responses):
    mock_db.get_session_messages.return_value = []
    mock_db.save_message.return_value = {"id": 1}
    mock_phase_db.increment_evasion_count.return_value = 0
    mock_db.get_session.side_effect = build_db_side_effect(len(user_messages))
    mock_llm.side_effect = [
        (text, 100, "claude") for text in llm_responses
    ]
    for msg in user_messages:
        process_chat(1, 1, msg)


def sig(signal):
    return f'Guide text.\n{{"phase_signal": "{signal}"}}'


class TestExitRouteScenarios:

    def test_seeking_reassurance(self):
        """Horror film: rejection / Expected: gibraltar (path_b)"""
        user_messages = [
            "I keep texting my friend to make sure she is not angry with me.",
            "She replied slowly and I cannot stop checking my phone.",
            "It calms it for a minute but it comes back.",
            "There is a tight pressure in my chest.",
            "The urge is still there but the pressure softened a little.",
        ]
        llm_responses = [sig("stay"), sig("advance"), sig("advance"), sig("advance"), sig("path_b")]

        with patch("services.chat_service.llm.call_claude") as mock_llm, \
             patch("services.chat_service.db") as mock_db, \
             patch("services.phase_engine.db") as mock_phase_db:
            run_turns(mock_llm, mock_db, mock_phase_db, user_messages, llm_responses)
            mock_phase_db.update_session_phase.assert_called_with(1, "gibraltar")

    def test_analyzing(self):
        """Horror film: failure / Expected: gibraltar (path_b)"""
        user_messages = [
            "I keep going over the presentation in my head trying to find what went wrong.",
            "If I figure out the mistake I can make sure it never happens again.",
            "People would think I am incompetent.",
            "There is a heaviness in my stomach.",
            "The thinking got quieter when I stayed with the heaviness.",
        ]
        llm_responses = [sig("advance"), sig("advance"), sig("advance"), sig("advance"), sig("path_b")]

        with patch("services.chat_service.llm.call_claude") as mock_llm, \
             patch("services.chat_service.db") as mock_db, \
             patch("services.phase_engine.db") as mock_phase_db:
            run_turns(mock_llm, mock_db, mock_phase_db, user_messages, llm_responses)
            mock_phase_db.update_session_phase.assert_called_with(1, "gibraltar")

    def test_reframing(self):
        """Horror film: humiliation / Expected: recurrence_normalization (path_a)"""
        user_messages = [
            "I keep trying to see it as a learning experience but it is not working.",
            "I said something embarrassing in a meeting and everyone noticed.",
            "It tries to make it not matter. But I keep coming back to it.",
            "I cannot find it. I just feel numb.",
        ]
        llm_responses = [sig("stay"), sig("advance"), sig("advance"), sig("path_a")]

        with patch("services.chat_service.llm.call_claude") as mock_llm, \
             patch("services.chat_service.db") as mock_db, \
             patch("services.phase_engine.db") as mock_phase_db:
            run_turns(mock_llm, mock_db, mock_phase_db, user_messages, llm_responses)
            mock_phase_db.update_session_phase.assert_called_with(1, "recurrence_normalization")

    def test_catastrophizing(self):
        """Horror film: loss of control / Expected: gibraltar (path_c)"""
        user_messages = [
            "I keep imagining everything falling apart — my job, my relationship, everything.",
            "If I prepare for the worst I will not be blindsided.",
            "My whole life feels unstable.",
            "My whole chest feels like it is bracing.",
            "The images slowed down. The bracing is still there but I am not fighting it.",
        ]
        llm_responses = [sig("advance"), sig("advance"), sig("advance"), sig("advance"), sig("path_c")]

        with patch("services.chat_service.llm.call_claude") as mock_llm, \
             patch("services.chat_service.db") as mock_db, \
             patch("services.phase_engine.db") as mock_phase_db:
            run_turns(mock_llm, mock_db, mock_phase_db, user_messages, llm_responses)
            mock_phase_db.update_session_phase.assert_called_with(1, "gibraltar")

    def test_excavating_the_past(self):
        """Horror film: exposure / Expected: gibraltar (path_b)"""
        user_messages = [
            "I think this goes back to my childhood. My parents never really saw me.",
            "It explains why I hide myself. But I am still hiding.",
            "I would feel too exposed.",
            "There is a kind of shrinking in my chest.",
            "The shrinking is still there but it feels less dangerous.",
        ]
        llm_responses = [sig("advance"), sig("advance"), sig("advance"), sig("advance"), sig("path_b")]

        with patch("services.chat_service.llm.call_claude") as mock_llm, \
             patch("services.chat_service.db") as mock_db, \
             patch("services.phase_engine.db") as mock_phase_db:
            run_turns(mock_llm, mock_db, mock_phase_db, user_messages, llm_responses)
            mock_phase_db.update_session_phase.assert_called_with(1, "gibraltar")

    def test_comparing_progress(self):
        """Horror film: failure / Expected: gibraltar (path_b)"""
        user_messages = [
            "Everyone else seems to be further along than me. I measure myself against them constantly.",
            "That I am falling behind. That I am not doing enough.",
            "That I am a failure. That I wasted my potential.",
            "There is a sinking feeling in my chest.",
            "I stopped comparing for a second. The sinking is still there but it is just a feeling.",
        ]
        llm_responses = [sig("stay"), sig("advance"), sig("advance"), sig("advance"), sig("path_b")]

        with patch("services.chat_service.llm.call_claude") as mock_llm, \
             patch("services.chat_service.db") as mock_db, \
             patch("services.phase_engine.db") as mock_phase_db:
            run_turns(mock_llm, mock_db, mock_phase_db, user_messages, llm_responses)
            mock_phase_db.update_session_phase.assert_called_with(1, "gibraltar")

    def test_seeking_certainty(self):
        """Horror film: loss of control / Expected: gibraltar (path_c)"""
        user_messages = [
            "I have been researching my symptoms for hours. I need to know what is wrong.",
            "It would stop the not-knowing. The uncertainty is unbearable.",
            "Like a hum of dread that will not stop.",
            "It is hard. The pull to search is strong.",
            "The hum is still there but I am not running from it. It is just a sensation.",
        ]
        llm_responses = [sig("stay"), sig("advance"), sig("advance"), sig("advance"), sig("path_c")]

        with patch("services.chat_service.llm.call_claude") as mock_llm, \
             patch("services.chat_service.db") as mock_db, \
             patch("services.phase_engine.db") as mock_phase_db:
            run_turns(mock_llm, mock_db, mock_phase_db, user_messages, llm_responses)
            mock_phase_db.update_session_phase.assert_called_with(1, "gibraltar")

    def test_meta_observing(self):
        """Horror film: exposure / Expected: gibraltar (path_b)"""
        user_messages = [
            "I keep watching myself in conversations — analyzing how I am coming across in real time.",
            "It keeps me from saying something wrong. But it makes me feel disconnected.",
            "I would say the wrong thing. People would see who I really am.",
            "There is a tightness behind my eyes and in my jaw.",
            "The watching slowed. Something loosened in my jaw.",
        ]
        llm_responses = [sig("stay"), sig("advance"), sig("advance"), sig("advance"), sig("path_b")]

        with patch("services.chat_service.llm.call_claude") as mock_llm, \
             patch("services.chat_service.db") as mock_db, \
             patch("services.phase_engine.db") as mock_phase_db:
            run_turns(mock_llm, mock_db, mock_phase_db, user_messages, llm_responses)
            mock_phase_db.update_session_phase.assert_called_with(1, "gibraltar")
