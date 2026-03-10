"""
Phase Engine — Clear Seeing Guide
Enforces gate sequence. The LLM suggests. The engine decides.

The LLM does not control its own phase.
The backend does.
"""
import re
import db

# ---------------------------------------------------------------------------
# Transition Map
# Forward only. No skipping. Fork at hold_both_forces.
# ---------------------------------------------------------------------------

TRANSITION_MAP = {
    "mirror": "examinability",
    "examinability": "activation_check",
    "activation_check": "orient",
    "recovery": "orient",
    "orient": "pointer",
    "pointer": "revolving_door",
    "revolving_door": "hold_both_forces",
    "hold_both_forces": None,  # fork point — PATH A/B/C determined here
    "courage_gate": "hittability",
    "hittability": "integration",
    "integration": "re_examination",
    "gibraltar": "re_examination",
    "re_examination": "recurrence_normalization",
    "recurrence_normalization": "complete",
    "complete": None,
}

# Evasion counter only runs from orient onward
EVASION_PHASES = {
    "orient", "pointer", "revolving_door", "hold_both_forces", "courage_gate",
    "hittability", "integration"
}
MAX_EVASIONS = 3

VALID_SIGNALS = {
    "advance", "stay", "path_a", "path_b", "path_c", "three_evasion_exit"
}

# ---------------------------------------------------------------------------
# Signal Parsing
# ---------------------------------------------------------------------------


def parse_signal(response_text):
    """
    Extracts phase_signal from LLM response JSON block.
    Returns signal string, or None if missing / malformed.

    Expected format anywhere in response:
        {"phase_signal": "advance"}
    """
    try:
        match = re.search(r'\{\s*"phase_signal"\s*:\s*"([^"]+)"\s*\}',
                          response_text)
        if match:
            signal = match.group(1).strip()
            if signal in VALID_SIGNALS:
                return signal
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Phase Transitions
# ---------------------------------------------------------------------------


def apply_signal(session, signal):
    """
    Validates signal against transition map and updates DB.
    Returns the new phase string.

    Rules:
    - three_evasion_exit always routes to PATH A recurrence_normalization
    - hold_both_forces is the fork: path_b/c -> gibraltar, else -> PATH A
    - advance -> follow TRANSITION_MAP
    - stay -> no change
    - path_a/b/c at non-fork phases -> treated as stay (guard)
    """
    current_phase = session.get("conversation_phase", "mirror")
    session_id = session["id"]

    # Three evasion exit — absolute, overrides everything
    if signal == "three_evasion_exit":
        db.update_session_phase(session_id, "recurrence_normalization")
        db.update_perceptual_state(session_id, "path_a")
        return "recurrence_normalization"

    # Fork at hold_both_forces
    if current_phase == "hold_both_forces":
        if signal in ("path_b", "path_c"):
            next_phase = "gibraltar"
            perceptual = signal
        else:
            # path_a, advance, stay, or anything unexpected — safe default PATH A
            next_phase = "recurrence_normalization"
            perceptual = "path_a"
        db.update_session_phase(session_id, next_phase)
        db.update_perceptual_state(session_id, perceptual)
        return next_phase

    # Standard advance
    if signal == "advance":
        next_phase = TRANSITION_MAP.get(current_phase)
        if next_phase:
            db.update_session_phase(session_id, next_phase)
            return next_phase

    # stay (or unrecognised signal at wrong phase) — no change
    return current_phase


# ---------------------------------------------------------------------------
# Evasion Counter
# ---------------------------------------------------------------------------


def check_evasion(session, signal):
    """
    If LLM signals an evasion occurred (stay while in evasion-counting phase),
    increments counter. Returns True if three_evasion_exit should trigger.

    The LLM signals evasion by outputting "stay" while in an evasion phase.
    The engine tracks count. At MAX_EVASIONS it overrides to PATH A exit.
    """
    current_phase = session.get("conversation_phase", "mirror")

    if current_phase not in EVASION_PHASES:
        return False

    if signal != "stay":
        return False

    new_count = db.increment_evasion_count(session["id"])
    return new_count >= MAX_EVASIONS


# ---------------------------------------------------------------------------
# Charge-Based Path Determination (called at hold_both_forces if no LLM signal)
# ---------------------------------------------------------------------------


def determine_path_from_charge(session):
    """
    Fallback path determination using entry vs exit charge delta.
    Used when LLM signal at hold_both_forces is ambiguous.
    Returns 'path_a' or 'path_b' (path_c requires explicit LLM signal).
    """
    entry = session.get("entry_charge")
    exit_c = session.get("exit_charge")

    if entry is None or exit_c is None:
        return "path_a"

    delta = entry - exit_c
    if delta >= 3:
        return "path_b"
    return "path_a"


# ---------------------------------------------------------------------------
# Main Entry Point for chat_service
# ---------------------------------------------------------------------------


def process_signal(session, response_text, message_id):
    """
    Full signal processing pipeline called after every LLM response.

    1. Parse signal from response
    2. If missing: log failure, default to stay
    3. Check evasion counter
    4. Apply signal to phase engine
    5. Return new phase, signal_found, and signal string

    Returns: (new_phase, signal_found, signal)
    """
    signal = parse_signal(response_text)
    signal_found = signal is not None

    if not signal_found:
        # Log parse failure, default to stay
        db.log_signal_parse_failure(message_id)
        signal = "stay"

    # Check if evasion threshold hit
    evasion_exit = check_evasion(session, signal)
    if evasion_exit:
        signal = "three_evasion_exit"

    new_phase = apply_signal(session, signal)
    return new_phase, signal_found, signal
