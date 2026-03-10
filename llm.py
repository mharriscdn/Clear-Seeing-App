import os
import anthropic

MODEL = "claude-sonnet-4-6"

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _client


def get_system_prompt():
    """Reads the system prompt from system_prompt.txt."""
    prompt_path = os.path.join(os.path.dirname(__file__), "system_prompt.txt")
    with open(prompt_path, "r") as f:
        return f.read().strip()


def call_claude(messages, session):
    """
    Calls Claude with the full system prompt and message history.
    messages: list of dicts with 'role' and 'content'
    session: session dict (available for Phase 2 context if needed)
    Returns: (response_text, token_count, model_name)
    """
    client = _get_client()
    system_prompt = get_system_prompt()

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=messages,
    )

    response_text = response.content[0].text
    # Rough token count: input + output usage
    token_count = response.usage.input_tokens + response.usage.output_tokens

    return response_text, token_count, MODEL
