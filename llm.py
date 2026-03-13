import os
import anthropic

MODEL = "claude-sonnet-4-6"

_client = None

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")

PHASE_MODULE_MAP = {
    "mirror":                   "phase_mirror.txt",
    "examinability":            "phase_examinability.txt",
    "activation_check":         "phase_activation_check.txt",
    "recovery":                 "phase_recovery.txt",
    "orient":                   "phase_orient.txt",
    "pointer":                  "phase_pointer.txt",
    "revolving_door":           "phase_revolving_door.txt",
    "hold_both_forces":         "phase_hold_both_forces.txt",
    "courage_gate":             "phase_courage_gate.txt",
    "hittability":              "phase_hittability.txt",
    "integration":              "phase_integration.txt",
    "gibraltar":                "phase_gibraltar.txt",
    "re_examination":           "phase_re_examination.txt",
    "recurrence_normalization": "phase_recurrence_normalization.txt",
    "complete":                 None,
}

TRANSITION_MAP = {
    "mirror":                   "examinability",
    "examinability":            "activation_check",
    "activation_check":         "orient",
    "recovery":                 "examinability",
    "orient":                   "pointer",
    "pointer":                  "revolving_door",
    "revolving_door":           "hold_both_forces",
    "hold_both_forces":         "courage_gate",
    "courage_gate":             "hittability",
    "hittability":              "integration",
    "integration":              "re_examination",
    "gibraltar":                "re_examination",
    "re_examination":           "recurrence_normalization",
    "recurrence_normalization": "complete",
    "complete":                 None,
}


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _client


def _load(filename):
    """Load a prompt file from the prompts directory."""
    with open(os.path.join(PROMPTS_DIR, filename), "r") as f:
        return f.read().strip()


def get_system_prompt(phase="mirror", signal_retry=False):
    """
    Assembles system prompt as a list of Anthropic content blocks.
    Each block carries cache_control so Anthropic can cache the prompt.

    Cached blocks (type ephemeral):
      - core.txt
      - current phase module
      - signal_instruction.txt

    Not cached:
      - next phase module appended on signal_retry (conditional, variable)

    Falls back to core + signal only if phase is 'complete' or unrecognised.
    """
    core = _load("core.txt")
    signal = _load("signal_instruction.txt")

    phase_file = PHASE_MODULE_MAP.get(phase)

    if phase_file:
        phase_module = _load(phase_file)
        blocks = [
            {"type": "text", "text": core,         "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": phase_module,  "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": signal,        "cache_control": {"type": "ephemeral"}},
        ]

        if signal_retry:
            next_phase = TRANSITION_MAP.get(phase)
            next_file = PHASE_MODULE_MAP.get(next_phase) if next_phase else None
            if next_file:
                next_module = _load(next_file)
                blocks.append({
                    "type": "text",
                    "text": f"--- NEXT PHASE (for reference) ---\n\n{next_module}",
                })

        return blocks

    # Fallback — phase is 'complete' or unrecognised
    return [
        {"type": "text", "text": core,   "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": signal, "cache_control": {"type": "ephemeral"}},
    ]


def call_claude(messages, session, signal_retry=False):
    """
    Calls Claude with an assembled modular system prompt (content blocks).
    messages: list of dicts with 'role' and 'content'
    session:  session dict — conversation_phase used to select phase module
    signal_retry: if True, next phase module is appended for context

    Returns a dict:
      {
        "content":      <assistant message text>,
        "input_tokens": int,
        "output_tokens": int,
        "cached_tokens": int,   # cache_read_input_tokens only
        "model":        str,
      }
    cache_creation_input_tokens is logged but not returned (not billed to user).
    """
    client = _get_client()
    phase = session.get("conversation_phase", "mirror") if session else "mirror"
    system_blocks = get_system_prompt(phase, signal_retry=signal_retry)

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system_blocks,
        messages=messages,
    )

    response_text = response.content[0].text
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    cached_tokens = getattr(response.usage, "cache_read_input_tokens", 0) or 0
    cache_creation = getattr(response.usage, "cache_creation_input_tokens", 0) or 0

    print(
        f"[llm] tokens — input={input_tokens} output={output_tokens} "
        f"cached={cached_tokens} cache_creation={cache_creation}"
    )

    return {
        "content":      response_text,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_tokens": cached_tokens,
        "model":        MODEL,
    }
