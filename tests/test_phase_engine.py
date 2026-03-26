"""
Clear Seeing Guide — Phase Engine Regression Test Suite v2
==========================================================
Tests the v2 prompt architecture:
  identity → mirror → contact → orient → revolving_door →
  hold_both_forces → (PATH B/C → hittability) →
  re_examination → recurrence_normalization

Six scenarios:
  S1 — Full PATH B session
  S2 — Full PATH C session
  S3 — PATH A exit via three-evasion
  S4 — Low charge entry (engine routing is charge-agnostic at this level)
  S5 — Recovery detour after contact
  S6 — Identity phase requires multiple stays before advance

Run with:  python -m pytest tests/test_phase_engine.py -v
"""

import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from services.phase_engine import (
    parse_signal,
    apply_signal,
    check_evasion,
    determine_path_from_charge,
    process_signal,
    VALID_SIGNALS,
    TRANSITION_MAP,
    EVASION_PHASES,
    MAX_EVASIONS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_session(phase="identity", perceptual_state="path_b",
                 entry_charge=8, exit_charge=3, session_id=1):
    return {
        "id": session_id,
        "conversation_phase": phase,
        "perceptual_state": perceptual_state,
        "entry_charge": entry_charge,
        "exit_charge": exit_charge,
    }


def step(session, signal):
    """Apply one signal, update session dict in place, return new phase."""
    with patch("services.phase_engine.db") as mock_db:
        mock_db.increment_evasion_count.return_value = 1
        new_phase = apply_signal(session, signal)
        # Capture perceptual_state if set
        if mock_db.update_perceptual_state.called:
            args = mock_db.update_perceptual_state.call_args[0]
            session["perceptual_state"] = args[1]
    session["conversation_phase"] = new_phase
    return new_phase


# ---------------------------------------------------------------------------
# SCENARIO 1 — Full PATH B session
# ---------------------------------------------------------------------------

class TestScenario1_PathB:
    """
    Charged entry (7+). Full gate sequence fires. PATH B at fork.
    Hold both forces → charge drops → PATH B → hittability directly.
    Deep hittability → finds just uncomfortable sensation, survivable → advance.
    Re-examination → situation workable, charge dropped.
    Recurrence normalization.

    Expected spine:
      identity → mirror → contact → orient → revolving_door →
      hold_both_forces --path_b--> hittability →
      re_examination → recurrence_normalization → complete
    """

    def test_full_path_b_sequence(self):
        s = make_session("identity", perceptual_state="path_b")
        steps = [
            ("advance", "mirror"),
            ("advance", "contact"),
            ("advance", "orient"),
            ("advance", "revolving_door"),
            ("advance", "hold_both_forces"),
            ("path_b",  "hittability"),
            ("advance", "re_examination"),
            ("advance", "recurrence_normalization"),
            ("advance", "complete"),
        ]
        for signal, expected in steps:
            result = step(s, signal)
            assert result == expected, \
                f"PATH B: after signal={signal!r} expected {expected!r}, got {result!r}"

    def test_perceptual_state_set_to_path_b_at_fork(self):
        s = make_session("hold_both_forces")
        step(s, "path_b")
        assert s["perceptual_state"] == "path_b"

    def test_gibraltar_routes_to_hittability(self):
        s = make_session("gibraltar", perceptual_state="path_b")
        assert step(s, "advance") == "hittability"

    def test_hittability_path_b_goes_to_re_examination_not_integration(self):
        s = make_session("hittability", perceptual_state="path_b")
        result = step(s, "advance")
        assert result == "re_examination", \
            "PATH B: hittability advance must go to re_examination, not integration"

    def test_re_examination_to_recurrence_normalization(self):
        s = make_session("re_examination")
        assert step(s, "advance") == "recurrence_normalization"


# ---------------------------------------------------------------------------
# SCENARIO 2 — Full PATH C session
# ---------------------------------------------------------------------------

class TestScenario2_PathC:
    """
    Self-dissolving response at hold_both_forces → PATH C.
    Deep hittability → nothing there to receive the hit → STATE 3 → advance.
    Re-examination and recurrence normalization.

    Expected spine:
      identity → mirror → contact → orient → revolving_door →
      hold_both_forces --path_c--> hittability →
      re_examination → recurrence_normalization → complete
    """

    def test_full_path_c_sequence(self):
        s = make_session("identity", perceptual_state="path_b")
        steps = [
            ("advance", "mirror"),
            ("advance", "contact"),
            ("advance", "orient"),
            ("advance", "revolving_door"),
            ("advance", "hold_both_forces"),
            ("path_c",  "hittability"),
            ("advance", "re_examination"),
            ("advance", "recurrence_normalization"),
            ("advance", "complete"),
        ]
        for signal, expected in steps:
            result = step(s, signal)
            assert result == expected, \
                f"PATH C: after signal={signal!r} expected {expected!r}, got {result!r}"

    def test_perceptual_state_set_to_path_c_at_fork(self):
        s = make_session("hold_both_forces")
        step(s, "path_c")
        assert s["perceptual_state"] == "path_c"

    def test_hittability_path_c_goes_to_re_examination(self):
        s = make_session("hittability", perceptual_state="path_c")
        result = step(s, "advance")
        assert result == "re_examination", \
            "PATH C: hittability advance must go to re_examination"

    def test_integration_to_re_examination(self):
        s = make_session("integration")
        assert step(s, "advance") == "re_examination"

    def test_path_b_and_path_c_both_fork_to_hittability(self):
        for path in ("path_b", "path_c"):
            s = make_session("hold_both_forces")
            result = step(s, path)
            assert result == "hittability", \
                f"{path} at hold_both_forces must route to hittability"


# ---------------------------------------------------------------------------
# SCENARIO 3 — PATH A exit via three evasions
# ---------------------------------------------------------------------------

class TestScenario3_ThreeEvasionExit:
    """
    User evades three times in an evasion-counting phase.
    three_evasion_exit fires → recurrence_normalization with path_a.
    Also covers: hold_both_forces without path_b/path_c defaults to PATH A.
    """

    def test_three_evasion_exit_routes_to_recurrence_normalization(self):
        s = make_session("orient")
        result = step(s, "three_evasion_exit")
        assert result == "recurrence_normalization"

    def test_three_evasion_exit_sets_path_a(self):
        s = make_session("orient")
        with patch("services.phase_engine.db") as mock_db:
            apply_signal(s, "three_evasion_exit")
            mock_db.update_perceptual_state.assert_called_once_with(s["id"], "path_a")

    def test_three_evasion_exit_overrides_any_phase(self):
        for phase in TRANSITION_MAP:
            s = make_session(phase)
            result = step(s, "three_evasion_exit")
            assert result == "recurrence_normalization", \
                f"three_evasion_exit must route to recurrence_normalization from {phase!r}"

    def test_check_evasion_returns_true_at_max(self):
        s = make_session("orient")
        with patch("services.phase_engine.db") as mock_db:
            mock_db.increment_evasion_count.return_value = MAX_EVASIONS
            assert check_evasion(s, "stay") is True

    def test_check_evasion_returns_false_below_max(self):
        s = make_session("orient")
        with patch("services.phase_engine.db") as mock_db:
            mock_db.increment_evasion_count.return_value = MAX_EVASIONS - 1
            assert check_evasion(s, "stay") is False

    def test_evasion_counter_not_triggered_by_advance(self):
        s = make_session("orient")
        with patch("services.phase_engine.db") as mock_db:
            check_evasion(s, "advance")
            mock_db.increment_evasion_count.assert_not_called()

    def test_hold_both_forces_advance_defaults_to_path_a(self):
        """Ambiguous/missing path signal at fork → safe default PATH A."""
        s = make_session("hold_both_forces")
        result = step(s, "advance")
        assert result == "recurrence_normalization"
        assert s["perceptual_state"] == "path_a"

    def test_hold_both_forces_path_a_signal_routes_to_recurrence(self):
        s = make_session("hold_both_forces")
        result = step(s, "path_a")
        assert result == "recurrence_normalization"
        assert s["perceptual_state"] == "path_a"

    def test_process_signal_evasion_threshold_triggers_path_a_exit(self):
        s = make_session("orient")
        with patch("services.phase_engine.db") as mock_db:
            mock_db.increment_evasion_count.return_value = MAX_EVASIONS
            new_phase, _, sig = process_signal(s, '{"phase_signal": "stay"}',
                                               message_id=1)
        assert new_phase == "recurrence_normalization"
        assert sig == "three_evasion_exit"


# ---------------------------------------------------------------------------
# SCENARIO 4 — Low charge entry
# ---------------------------------------------------------------------------

class TestScenario4_LowCharge:
    """
    Engine routing is charge-agnostic — charge doesn't change phase transitions.
    Low charge (1-3) changes LLM behaviour at mirror, but the engine still
    advances/stays the same way. Confirm engine correctness at low charge.
    """

    def test_identity_advances_with_low_charge(self):
        s = make_session("identity", entry_charge=2, exit_charge=1)
        assert step(s, "advance") == "mirror"

    def test_mirror_stay_holds_with_low_charge(self):
        s = make_session("mirror", entry_charge=2, exit_charge=1)
        assert step(s, "stay") == "mirror"

    def test_mirror_advance_goes_to_contact(self):
        s = make_session("mirror", entry_charge=2, exit_charge=1)
        assert step(s, "advance") == "contact"

    def test_determine_path_from_charge_low_delta_returns_path_a(self):
        s = make_session(entry_charge=3, exit_charge=2)
        assert determine_path_from_charge(s) == "path_a"

    def test_determine_path_from_charge_high_delta_returns_path_b(self):
        s = make_session(entry_charge=9, exit_charge=2)
        assert determine_path_from_charge(s) == "path_b"

    def test_determine_path_from_charge_missing_entry_returns_path_a(self):
        s = make_session(entry_charge=None, exit_charge=2)
        assert determine_path_from_charge(s) == "path_a"

    def test_determine_path_from_charge_missing_exit_returns_path_a(self):
        s = make_session(entry_charge=5, exit_charge=None)
        assert determine_path_from_charge(s) == "path_a"

    def test_determine_path_from_charge_delta_exactly_3_returns_path_b(self):
        s = make_session(entry_charge=6, exit_charge=3)
        assert determine_path_from_charge(s) == "path_b"


# ---------------------------------------------------------------------------
# SCENARIO 5 — Recovery detour after contact
# ---------------------------------------------------------------------------

class TestScenario5_RecoveryDetour:
    """
    User floods after contact phase. Recovery routes back to orient on advance.
    contact → [flood detected by LLM] → recovery → orient → spine continues.
    """

    def test_recovery_advance_routes_to_orient(self):
        s = make_session("recovery")
        assert step(s, "advance") == "orient", \
            "recovery advance must return to orient"

    def test_recovery_stay_holds_in_recovery(self):
        s = make_session("recovery")
        assert step(s, "stay") == "recovery"

    def test_contact_stay_stays_at_contact(self):
        s = make_session("contact")
        assert step(s, "stay") == "contact"

    def test_contact_advance_goes_to_orient(self):
        s = make_session("contact")
        assert step(s, "advance") == "orient"

    def test_recovery_not_in_evasion_phases(self):
        """Recovery is a detour — evasion counter must not fire here."""
        assert "recovery" not in EVASION_PHASES

    def test_contact_not_in_evasion_phases(self):
        assert "contact" not in EVASION_PHASES

    def test_recovery_returns_to_spine_after_detour(self):
        """Simulate: contact → recovery detour → back to orient → spine continues."""
        s = make_session("contact")
        step(s, "advance")                         # contact → orient (normal path)
        assert s["conversation_phase"] == "orient"

        # Now simulate detour: engine manually routes to recovery
        s["conversation_phase"] = "recovery"
        step(s, "advance")                         # recovery → orient
        assert s["conversation_phase"] == "orient"

        step(s, "advance")                         # orient → revolving_door
        assert s["conversation_phase"] == "revolving_door"


# ---------------------------------------------------------------------------
# SCENARIO 6 — Identity phase requires multiple turns
# ---------------------------------------------------------------------------

class TestScenario6_IdentityMultipleTurns:
    """
    User stays at surface consequence level. Identity phase holds (stay)
    until existential verdict is named, then advances to mirror.
    """

    def test_identity_stay_holds_at_identity(self):
        s = make_session("identity")
        assert step(s, "stay") == "identity"

    def test_identity_multiple_stays_before_advance(self):
        s = make_session("identity")
        step(s, "stay")
        step(s, "stay")
        step(s, "stay")
        assert s["conversation_phase"] == "identity"
        assert step(s, "advance") == "mirror"

    def test_identity_not_in_evasion_phases(self):
        """Identity is pre-evasion — stays must not increment counter."""
        assert "identity" not in EVASION_PHASES

    def test_identity_stay_does_not_trigger_evasion(self):
        s = make_session("identity")
        with patch("services.phase_engine.db") as mock_db:
            check_evasion(s, "stay")
            mock_db.increment_evasion_count.assert_not_called()

    def test_identity_advance_goes_to_mirror_not_contact(self):
        """Identity must go directly to mirror, not skip ahead."""
        s = make_session("identity")
        assert step(s, "advance") == "mirror"

    def test_mirror_stay_holds_if_film_not_yet_named(self):
        s = make_session("mirror")
        assert step(s, "stay") == "mirror"

    def test_mirror_advance_goes_to_contact(self):
        s = make_session("mirror")
        assert step(s, "advance") == "contact"


# ---------------------------------------------------------------------------
# Signal Parser
# ---------------------------------------------------------------------------

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
        assert parse_signal('{"phase_signal": "three_evasion_exit"}') == "three_evasion_exit"

    def test_signal_embedded_in_prose(self):
        text = 'Coaching text here. {"phase_signal": "advance"} More text.'
        assert parse_signal(text) == "advance"

    def test_whitespace_tolerant(self):
        assert parse_signal('{ "phase_signal" : "stay" }') == "stay"

    def test_unknown_signal_returns_none(self):
        assert parse_signal('{"phase_signal": "jump"}') is None

    def test_missing_block_returns_none(self):
        assert parse_signal("No signal here.") is None

    def test_empty_string_returns_none(self):
        assert parse_signal("") is None

    def test_all_valid_signals_parse(self):
        for sig in VALID_SIGNALS:
            result = parse_signal(f'{{"phase_signal": "{sig}"}}')
            assert result == sig, f"Expected {sig!r}, got {result!r}"


# ---------------------------------------------------------------------------
# Transition Map Integrity
# ---------------------------------------------------------------------------

class TestTransitionMapIntegrity:
    """Guard: map is v2-only. Old phase names must be absent."""

    REMOVED_PHASES = {"examinability", "activation_check", "pointer", "courage_gate"}
    NEW_PHASES = {"identity", "contact"}

    def test_removed_phases_not_in_map(self):
        for phase in self.REMOVED_PHASES:
            assert phase not in TRANSITION_MAP, \
                f"Old phase {phase!r} must not appear in TRANSITION_MAP"

    def test_new_phases_in_map(self):
        for phase in self.NEW_PHASES:
            assert phase in TRANSITION_MAP, \
                f"New phase {phase!r} must be in TRANSITION_MAP"

    def test_identity_routes_to_mirror(self):
        assert TRANSITION_MAP["identity"] == "mirror"

    def test_mirror_routes_to_contact(self):
        assert TRANSITION_MAP["mirror"] == "contact"

    def test_contact_routes_to_orient(self):
        assert TRANSITION_MAP["contact"] == "orient"

    def test_orient_routes_to_revolving_door(self):
        assert TRANSITION_MAP["orient"] == "revolving_door", \
            "orient must skip pointer — pointer removed in v2"

    def test_revolving_door_routes_to_hold_both_forces(self):
        assert TRANSITION_MAP["revolving_door"] == "hold_both_forces"

    def test_hold_both_forces_is_fork(self):
        assert TRANSITION_MAP["hold_both_forces"] is None

    def test_gibraltar_routes_to_hittability(self):
        assert TRANSITION_MAP["gibraltar"] == "hittability", \
            "gibraltar must go to hittability (not re_examination as in v1)"

    def test_hittability_is_fork(self):
        assert TRANSITION_MAP["hittability"] is None, \
            "hittability is a fork (both PATH B and PATH C → re_examination)"

    def test_integration_routes_to_re_examination(self):
        assert TRANSITION_MAP["integration"] == "re_examination"

    def test_re_examination_routes_to_recurrence_normalization(self):
        assert TRANSITION_MAP["re_examination"] == "recurrence_normalization"

    def test_removed_phases_not_in_evasion_phases(self):
        for phase in self.REMOVED_PHASES:
            assert phase not in EVASION_PHASES, \
                f"Old phase {phase!r} must not be in EVASION_PHASES"

    def test_orient_is_evasion_phase(self):
        assert "orient" in EVASION_PHASES

    def test_revolving_door_is_evasion_phase(self):
        assert "revolving_door" in EVASION_PHASES

    def test_hittability_is_evasion_phase(self):
        assert "hittability" in EVASION_PHASES


# ---------------------------------------------------------------------------
# process_signal (full pipeline)
# ---------------------------------------------------------------------------

class TestProcessSignal:

    def test_valid_signal_returns_new_phase_and_found_true(self):
        s = make_session("identity")
        with patch("services.phase_engine.db") as mock_db:
            new_phase, found, _ = process_signal(s, '{"phase_signal": "advance"}',
                                                 message_id=1)
        assert found is True
        assert new_phase == "mirror"

    def test_missing_signal_defaults_to_stay(self):
        s = make_session("mirror")
        with patch("services.phase_engine.db") as mock_db:
            new_phase, found, _ = process_signal(s, "No signal here.", message_id=1)
        assert found is False
        assert new_phase == "mirror"

    def test_missing_signal_logs_parse_failure(self):
        s = make_session("mirror")
        with patch("services.phase_engine.db") as mock_db:
            process_signal(s, "No signal here.", message_id=42)
            mock_db.log_signal_parse_failure.assert_called_once_with(42)

    def test_stay_below_evasion_threshold_holds_phase(self):
        s = make_session("orient")
        with patch("services.phase_engine.db") as mock_db:
            mock_db.increment_evasion_count.return_value = MAX_EVASIONS - 1
            new_phase, _, _ = process_signal(s, '{"phase_signal": "stay"}',
                                             message_id=1)
        assert new_phase == "orient"

    def test_db_not_updated_on_stay(self):
        s = make_session("mirror")
        with patch("services.phase_engine.db") as mock_db:
            apply_signal(s, "stay")
            mock_db.update_session_phase.assert_not_called()

    def test_db_updated_on_advance(self):
        s = make_session("identity")
        with patch("services.phase_engine.db") as mock_db:
            apply_signal(s, "advance")
            mock_db.update_session_phase.assert_called_once_with(s["id"], "mirror")
