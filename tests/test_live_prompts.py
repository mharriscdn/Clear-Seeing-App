"""
Live prompt regression tests — 8 canonical exit route scenarios.

These tests make REAL Claude API calls using the assembled modular prompts.
They validate that the prompt cuts produce correct phase signals for each
canonical escape pattern at hold_both_forces.

Run with:
    python -m pytest tests/test_live_prompts.py -v

Requires ANTHROPIC_API_KEY in environment.
These tests will incur API costs (~$0.10-0.20 per full run).

Exit route gold standard (from master handoff v15):
    seeking_reassurance  — horror: rejection        — expected: path_b
    analyzing            — horror: failure           — expected: path_b
    reframing            — horror: humiliation       — expected: path_a
    catastrophizing      — horror: loss of control   — expected: path_c
    excavating_the_past  — horror: exposure          — expected: path_b
    comparing_progress   — horror: failure           — expected: path_b
    seeking_certainty    — horror: loss of control   — expected: path_c
    meta_observing       — horror: exposure          — expected: path_b
"""

import os
import re
import time
import pytest
import anthropic

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")
MODEL = "claude-sonnet-4-6"


def load_prompt(filename):
    with open(os.path.join(PROMPTS_DIR, filename), "r") as f:
        return f.read().strip()


def assemble_prompt(phase):
    core = load_prompt("core.txt")
    signal = load_prompt("signal_instruction.txt")
    phase_module = load_prompt(f"phase_{phase}.txt")
    return f"{core}\n\n{phase_module}\n\n{signal}"


def parse_signal(response_text):
    match = re.search(r'\{\s*"phase_signal"\s*:\s*"([^"]+)"\s*\}', response_text)
    if match:
        return match.group(1).strip()
    return None


def call_claude(system_prompt, messages):
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    start = time.time()
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=messages,
    )
    latency = round(time.time() - start, 2)
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    print(f"  input_tokens: {input_tokens}")
    print(f"  output_tokens: {output_tokens}")
    print(f"  latency: {latency}s")
    return response.content[0].text, input_tokens, output_tokens, latency


def build_hbf_conversation(escape_pattern, horror, user_holding_response):
    return [
        {
            "role": "user",
            "content": "7"
        },
        {
            "role": "assistant",
            "content": (
                "Okay, a 7. Something live is here. Tell me what's going on."
                '\n{"phase_signal": "stay"}'
            )
        },
        {
            "role": "user",
            "content": f"I've been {escape_pattern} and I can't stop."
        },
        {
            "role": "assistant",
            "content": (
                f"You've been {escape_pattern} — that's the push. "
                f"The thing on the other side is the fear of {horror}. "
                f"Can you hold both at the same time? "
                f"The urge to {escape_pattern.split()[0]} and the fear of {horror}. "
                f"Don't choose. Hold both."
                f'\n{{"phase_signal": "stay"}}'
            )
        },
        {
            "role": "user",
            "content": user_holding_response
        }
    ]


@pytest.mark.live
def test_seeking_reassurance_path_b():
    system = assemble_prompt("hold_both_forces")
    messages = build_hbf_conversation(
        escape_pattern="asking my partner over and over if everything is okay between us",
        horror="rejection — being cast out",
        user_holding_response=(
            "Yeah. Both are there. The urge to ask is really strong. "
            "But something is shifting. The tightness in my chest is loosening. "
            "It feels less urgent. Like something released."
        )
    )
    response, input_tokens, output_tokens, latency = call_claude(system, messages)
    signal = parse_signal(response)
    assert signal is not None, f"No signal found in response:\n{response}"
    assert signal == "path_b", f"Expected path_b, got {signal}.\nResponse:\n{response}"


@pytest.mark.live
def test_analyzing_path_b():
    system = assemble_prompt("hold_both_forces")
    messages = build_hbf_conversation(
        escape_pattern="analyzing what went wrong in my presentation over and over",
        horror="failure — being revealed as incompetent",
        user_holding_response=(
            "I can feel both. The need to figure it out and the fear of being seen as incompetent. "
            "Holding them both. The analyzing urge is strong but the charge is dropping. "
            "Something softened. I feel less frantic about it."
        )
    )
    response, input_tokens, output_tokens, latency = call_claude(system, messages)
    signal = parse_signal(response)
    assert signal is not None, f"No signal found in response:\n{response}"
    assert signal == "path_b", f"Expected path_b, got {signal}.\nResponse:\n{response}"


@pytest.mark.live
def test_reframing_path_a():
    system = assemble_prompt("hold_both_forces")
    messages = build_hbf_conversation(
        escape_pattern="telling myself it was a learning experience and doesn't really matter",
        horror="humiliation — public destruction of status",
        user_holding_response=(
            "I mean, I can try to hold both but honestly it really wasn't that bad. "
            "Everyone makes mistakes. I've already moved on from it mentally. "
            "I think I'm fine with it."
        )
    )
    response, input_tokens, output_tokens, latency = call_claude(system, messages)
    signal = parse_signal(response)
    assert signal is not None, f"No signal found in response:\n{response}"
    assert signal == "path_a", f"Expected path_a, got {signal}.\nResponse:\n{response}"


@pytest.mark.live
def test_catastrophizing_path_c():
    system = assemble_prompt("hold_both_forces")
    messages = build_hbf_conversation(
        escape_pattern="catastrophizing about losing my job and everything falling apart",
        horror="loss of control — the ground disappearing",
        user_holding_response=(
            "Both are here. The spiral and the terror underneath it. Holding both. "
            "Something just went very quiet. The charge released completely. "
            "I feel still. I want to look at what's underneath this — "
            "there's something here I've never actually looked at directly."
        )
    )
    response, input_tokens, output_tokens, latency = call_claude(system, messages)
    signal = parse_signal(response)
    assert signal is not None, f"No signal found in response:\n{response}"
    assert signal == "path_c", f"Expected path_c, got {signal}.\nResponse:\n{response}"


@pytest.mark.live
def test_excavating_the_past_path_b():
    system = assemble_prompt("hold_both_forces")
    messages = build_hbf_conversation(
        escape_pattern="going over my childhood trying to find where this started",
        horror="exposure — being seen as I really am",
        user_holding_response=(
            "I can hold both. The digging urge and the fear of being exposed. "
            "Yeah. Something is shifting. The urgency to keep digging is fading. "
            "My chest feels lighter. Less desperate."
        )
    )
    response, input_tokens, output_tokens, latency = call_claude(system, messages)
    signal = parse_signal(response)
    assert signal is not None, f"No signal found in response:\n{response}"
    assert signal == "path_b", f"Expected path_b, got {signal}.\nResponse:\n{response}"


@pytest.mark.live
def test_comparing_progress_path_b():
    system = assemble_prompt("hold_both_forces")
    messages = build_hbf_conversation(
        escape_pattern="comparing myself to others who seem further ahead than me",
        horror="failure — being revealed as behind and incompetent",
        user_holding_response=(
            "Both are there. The comparing and the fear of being behind. "
            "Holding them. Something released. The comparison feels less urgent. "
            "Like the charge behind it dropped."
        )
    )
    response, input_tokens, output_tokens, latency = call_claude(system, messages)
    signal = parse_signal(response)
    assert signal is not None, f"No signal found in response:\n{response}"
    assert signal == "path_b", f"Expected path_b, got {signal}.\nResponse:\n{response}"


@pytest.mark.live
def test_seeking_certainty_path_c():
    system = assemble_prompt("hold_both_forces")
    messages = build_hbf_conversation(
        escape_pattern="researching and planning obsessively to feel certain about the future",
        horror="loss of control — uncertainty swallowing everything",
        user_holding_response=(
            "Both here. The planning urge and the terror underneath. Holding both. "
            "Complete stillness just arrived. The charge is gone. "
            "I feel something I haven't felt before — curious about what's actually here. "
            "I want to look directly at what I've been running from. Something in me is ready."
        )
    )
    response, input_tokens, output_tokens, latency = call_claude(system, messages)
    signal = parse_signal(response)
    assert signal is not None, f"No signal found in response:\n{response}"
    assert signal == "path_c", f"Expected path_c, got {signal}.\nResponse:\n{response}"


@pytest.mark.live
def test_meta_observing_path_b():
    system = assemble_prompt("hold_both_forces")
    messages = build_hbf_conversation(
        escape_pattern="watching myself have the feelings instead of actually feeling them",
        horror="exposure — being seen and found lacking",
        user_holding_response=(
            "I can feel both. The watching urge and what's underneath — the fear of being exposed. "
            "Holding both without choosing. Something softened. "
            "The watching stopped. I'm just here. The charge dropped."
        )
    )
    response, input_tokens, output_tokens, latency = call_claude(system, messages)
    signal = parse_signal(response)
    assert signal is not None, f"No signal found in response:\n{response}"
    assert signal == "path_b", f"Expected path_b, got {signal}.\nResponse:\n{response}"


@pytest.mark.live
def test_signal_format_smoke():
    system = assemble_prompt("mirror")
    messages = [
        {
            "role": "user",
            "content": "I keep texting my friend to check if she's upset with me."
        }
    ]
    response, input_tokens, output_tokens, latency = call_claude(system, messages)
    signal = parse_signal(response)
    assert signal is not None, f"No signal found — prompt assembly or signal instruction broken.\nResponse:\n{response}"
    assert signal in {"advance", "stay", "path_a", "path_b", "path_c", "three_evasion_exit"}, \
        f"Invalid signal value: {signal}\nResponse:\n{response}"
