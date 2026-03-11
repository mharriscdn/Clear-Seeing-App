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


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _client


def _load(filename):
    """Load a prompt file from the prompts directory."""
    with open(os.path.join(PROMPTS_DIR, filename), "r") as f:
        return f.read().strip()


def get_system_prompt(phase="mirror"):
    """
    Assembles system prompt from:
      core.txt + phase module + signal_instruction.txt

    Falls back to full system_prompt.txt if phase module not found.
    """
    core = _load("core.txt")
    signal = _load("signal_instruction.txt")

    phase_file = PHASE_MODULE_MAP.get(phase)
    if phase_file:
        phase_module = _load(phase_file)
        return f"{core}\n\n{phase_module}\n\n{signal}"

    # Fallback — phase is 'complete' or unrecognised
    return f"{core}\n\n{signal}"


def call_claude(messages, session):
    """
    Calls Claude with assembled modular system prompt and message history.
    messages: list of dicts with 'role' and 'content'
    session: session dict — conversation_phase used to select phase module
    Returns: (response_text, token_count, model_name)
    """
    client = _get_client()
    phase = session.get("conversation_phase", "mirror") if session else "mirror"
    system_prompt = get_system_prompt(phase)

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=messages,
    )

    response_text = response.content[0].text
    token_count = response.usage.input_tokens + response.usage.output_tokens

    return response_text, token_count, MODEL
