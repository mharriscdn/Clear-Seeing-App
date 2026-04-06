import os
import anthropic

MODEL = "claude-sonnet-4-6"

_client = None

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "services/prompts")


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _client


def _load_session_prompt():
    path = os.path.join(PROMPTS_DIR, "session.txt")
    with open(path, "r") as f:
        return f.read().strip()


def call_claude(messages):
    """
    Calls Claude with the v9 session prompt as a single cached system block.
    messages: list of dicts with 'role' and 'content'

    Returns a dict:
      {
        "content":      <assistant message text>,
        "input_tokens": int,
        "output_tokens": int,
        "cached_tokens": int,
        "model":        str,
      }
    """
    client = _get_client()
    system_prompt = _load_session_prompt()
    system_blocks = [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }
    ]

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
