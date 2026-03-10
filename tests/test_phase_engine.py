"""
Tests for services/phase_engine.py

All db calls are mocked so no database connection is required.
Run with: python -m pytest tests/test_phase_engine.py -v
"""
import sys
import os
import types
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_session(phase="mirror",
                 entry_charge=None,
                 exit_charge=None,
                 session_id=1):
    return {
        "id": session_id,
        "conversation_phase": phase,
        "entry_charge": entry_charge,
        "exit_charge": exit_charge,
    }


# ---------------------------------------------------------------------------
# parse_signal
# ---------------------------------------------------------------------------

from services.phase_engine import parse_signal, VALID_SIGNALS, TRANSITION_MAP


class TestParseSignal:

    def test_advance(self):
        assert parse_signal('{"phase_signal": "advance"}') == "advance"

    def test_stay(self):
        assert parse_signal('{"phase_signal": "stay"}') == "stay"

    def test_path_a(self):
        assert parse_signal('{"phase_signal": "path_a"}') == "path_a"

    def test_path_b(self):
        assert parse_signal('{"phase_signal": "path_b"}') == "path_b"

    def test_path_c(self):
        assert parse_signal('{"phase_signal": "path_c"}') == "path_c"

    def test_three_evasion_exit(self):
        assert parse_signal(
            '{"phase_signal": "three_evasion_exit"}') == "three_evasion_exit"

    def test_signal_embedded_in_prose(self):
        text = 'Some coaching text here. {"phase_signal": "advance"} More text.'
        assert parse_signal(text) == "advance"

    def test_signal_with_extra_whitespace(self):
        assert parse_signal('{ "phase_signal" : "stay" }') == "stay"

    def test_unknown_signal_returns_none(self):
        assert parse_signal('{"phase_signal": "jump"}') is None

    def test_missing_signal_returns_none(self):
        assert parse_signal("No signal here at all.") is None

    def test_empty_string_returns_none(self):
        assert parse_signal("") is None

    def test_malformed_json_returns_none(self):
        assert parse_signal('{"phase_signal": }') is None

    def test_all_valid_signals_parse(self):
        for sig in VALID_SIGNALS:
            result = parse_signal(f'{{"phase_signal": "{sig}"}}')
            assert result == sig, f"Expected {sig}, got {result}"


# ---------------------------------------------------------------------------
# apply_signal
# ---------------------------------------------------------------------------

from services.phase_engine import apply_signal


class TestApplySignal:

    def test_advance_follows_transition_map(self):
        for phase, expected_next in TRANSITION_MAP.items():
            if expected_next is None:
                continue
            if phase == "hold_both_forces":
                continue
            session = make_session(phase=phase)
            with patch("services.phase_engine.db") as mock_db:
                result = apply_signal(session, "advance")
            assert result == expected_next, f"From {phase}: expected {expected_next}, got {result}"

    def test_stay_returns_current_phase(self):
        for phase in TRANSITION_MAP:
            if phase == "hold_both_forces":
                continue
            session = make_session(phase=phase)
            with patch("services.phase_engine.db"):
                result = apply_signal(session, "stay")
            assert result == phase

    def test_stay_at_fork_treated_as_path_a(self):
        session = make_session(phase="hold_both_forces")
        with patch("services.phase_engine.db"):
            result = apply_signal(session, "stay")
        assert result == "recurrence_normalization"

    def test_three_evasion_exit_always_routes_to_recurrence_normalization(
            self):
        for phase in TRANSITION_MAP:
            session = make_session(phase=phase)
            with patch("services.phase_engine.db") as mock_db:
                result = apply_signal(session, "three_evasion_exit")
            assert result == "recurrence_normalization"

    def test_three_evasion_exit_sets_path_a(self):
        session = make_session(phase="orient")
        with patch("services.phase_engine.db") as mock_db:
            apply_signal(session, "three_evasion_exit")
            mock_db.update_perceptual_state.assert_called_once_with(
                session["id"], "path_a")

    def test_fork_path_b_routes_to_gibraltar(self):
        session = make_session(phase="hold_both_forces")
        with patch("services.phase_engine.db") as mock_db:
            result = apply_signal(session, "path_b")
        assert result == "gibraltar"

    def test_fork_path_c_routes_to_gibraltar(self):
        session = make_session(phase="hold_both_forces")
        with patch("services.phase_engine.db") as mock_db:
            result = apply_signal(session, "path_c")
        assert result == "gibraltar"

    def test_fork_path_a_routes_to_recurrence_normalization(self):
        session = make_session(phase="hold_both_forces")
        with patch("services.phase_engine.db") as mock_db:
            result = apply_signal(session, "path_a")
        assert result == "recurrence_normalization"

    def test_fork_advance_defaults_to_path_a(self):
        session = make_session(phase="hold_both_forces")
        with patch("services.phase_engine.db") as mock_db:
            result = apply_signal(session, "advance")
        assert result == "recurrence_normalization"

    def test_path_b_at_non_fork_phase_treated_as_stay(self):
        session = make_session(phase="mirror")
        with patch("services.phase_engine.db"):
            result = apply_signal(session, "path_b")
        assert result == "mirror"

    def test_advance_at_terminal_phase_returns_same_phase(self):
        session = make_session(phase="complete")
        with patch("services.phase_engine.db"):
            result = apply_signal(session, "advance")
        assert result == "complete"

    def test_db_update_called_on_advance(self):
        session = make_session(phase="mirror")
        with patch("services.phase_engine.db") as mock_db:
            apply_signal(session, "advance")
            mock_db.update_session_phase.assert_called_once_with(
                session["id"], "examinability")

    def test_db_not_updated_on_stay(self):
        session = make_session(phase="mirror")
        with patch("services.phase_engine.db") as mock_db:
            apply_signal(session, "stay")
            mock_db.update_session_phase.assert_not_called()


# ---------------------------------------------------------------------------
# check_evasion
# ---------------------------------------------------------------------------

from services.phase_engine import check_evasion, EVASION_PHASES, MAX_EVASIONS


class TestCheckEvasion:

    def test_stay_in_evasion_phase_increments_counter(self):
        for phase in EVASION_PHASES:
            session = make_session(phase=phase)
            with patch("services.phase_engine.db") as mock_db:
                mock_db.increment_evasion_count.return_value = 1
                check_evasion(session, "stay")
                mock_db.increment_evasion_count.assert_called_once_with(
                    session["id"])

    def test_advance_in_evasion_phase_does_not_increment(self):
        session = make_session(phase="orient")
        with patch("services.phase_engine.db") as mock_db:
            check_evasion(session, "advance")
            mock_db.increment_evasion_count.assert_not_called()

    def test_stay_in_non_evasion_phase_does_not_increment(self):
        session = make_session(phase="mirror")
        with patch("services.phase_engine.db") as mock_db:
            check_evasion(session, "stay")
            mock_db.increment_evasion_count.assert_not_called()

    def test_returns_false_below_max_evasions(self):
        session = make_session(phase="orient")
        with patch("services.phase_engine.db") as mock_db:
            mock_db.increment_evasion_count.return_value = MAX_EVASIONS - 1
            result = check_evasion(session, "stay")
        assert result is False

    def test_returns_true_at_max_evasions(self):
        session = make_session(phase="orient")
        with patch("services.phase_engine.db") as mock_db:
            mock_db.increment_evasion_count.return_value = MAX_EVASIONS
            result = check_evasion(session, "stay")
        assert result is True

    def test_returns_true_above_max_evasions(self):
        session = make_session(phase="orient")
        with patch("services.phase_engine.db") as mock_db:
            mock_db.increment_evasion_count.return_value = MAX_EVASIONS + 1
            result = check_evasion(session, "stay")
        assert result is True


# ---------------------------------------------------------------------------
# determine_path_from_charge
# ---------------------------------------------------------------------------

from services.phase_engine import determine_path_from_charge


class TestDeterminePathFromCharge:

    def test_delta_gte_3_returns_path_b(self):
        session = make_session(entry_charge=8, exit_charge=5)
        assert determine_path_from_charge(session) == "path_b"

    def test_delta_exactly_3_returns_path_b(self):
        session = make_session(entry_charge=6, exit_charge=3)
        assert determine_path_from_charge(session) == "path_b"

    def test_delta_lt_3_returns_path_a(self):
        session = make_session(entry_charge=5, exit_charge=4)
        assert determine_path_from_charge(session) == "path_a"

    def test_delta_zero_returns_path_a(self):
        session = make_session(entry_charge=5, exit_charge=5)
        assert determine_path_from_charge(session) == "path_a"

    def test_missing_entry_charge_returns_path_a(self):
        session = make_session(entry_charge=None, exit_charge=5)
        assert determine_path_from_charge(session) == "path_a"

    def test_missing_exit_charge_returns_path_a(self):
        session = make_session(entry_charge=5, exit_charge=None)
        assert determine_path_from_charge(session) == "path_a"

    def test_both_missing_returns_path_a(self):
        session = make_session(entry_charge=None, exit_charge=None)
        assert determine_path_from_charge(session) == "path_a"


# ---------------------------------------------------------------------------
# process_signal (full pipeline)
# ---------------------------------------------------------------------------

from services.phase_engine import process_signal


class TestProcessSignal:

    def test_valid_signal_returns_new_phase_and_found_true(self):
        session = make_session(phase="mirror")
        with patch("services.phase_engine.db") as mock_db:
            new_phase, found = process_signal(session,
                                              '{"phase_signal": "advance"}',
                                              message_id=1)
        assert found is True
        assert new_phase == "examinability"

    def test_missing_signal_defaults_to_stay(self):
        session = make_session(phase="mirror")
        with patch("services.phase_engine.db") as mock_db:
            new_phase, found = process_signal(session,
                                              "No signal here.",
                                              message_id=1)
        assert found is False
        assert new_phase == "mirror"

    def test_missing_signal_logs_parse_failure(self):
        session = make_session(phase="mirror")
        with patch("services.phase_engine.db") as mock_db:
            process_signal(session, "No signal here.", message_id=42)
            mock_db.log_signal_parse_failure.assert_called_once_with(42)

    def test_evasion_threshold_triggers_exit(self):
        session = make_session(phase="orient")
        with patch("services.phase_engine.db") as mock_db:
            mock_db.increment_evasion_count.return_value = MAX_EVASIONS
            new_phase, _ = process_signal(session,
                                          '{"phase_signal": "stay"}',
                                          message_id=1)
        assert new_phase == "recurrence_normalization"

    def test_stay_below_evasion_threshold_holds_phase(self):
        session = make_session(phase="orient")
        with patch("services.phase_engine.db") as mock_db:
            mock_db.increment_evasion_count.return_value = MAX_EVASIONS - 1
            new_phase, _ = process_signal(session,
                                          '{"phase_signal": "stay"}',
                                          message_id=1)
        assert new_phase == "orient"
