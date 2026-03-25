"""
Clear Seeing Guide — LLM Behavior Test Suite v2
================================================
Tests whether the LLM actually follows prompt instructions — not just whether
signals fire correctly. Each test calls the real Claude API with a crafted
conversation, then inspects the response for specific compliance criteria.

Ten tests covering the v2 prompt architecture:
  T1  — identity_pushes_to_verdict
  T2  — mirror_fires_after_identity
  T3  — body_question_after_mirror
  T4  — orient_existential_and_evidence_recruitment
  T5  — revolving_door_one_tension_not_two_body_locations
  T6  — path_b_routes_to_hittability (not skipped to re-examination)
  T7  — recognition_1_exit_door_named_not_explained
  T8  — sock_moment_path_b
  T9  — recurrence_normalization_specific
  T10 — recognition_already_knew (conditional line)

Requires: ANTHROPIC_API_KEY in environment.
Cost:      ~$0.20–$0.40 per full run.
Run with:  python -m pytest tests/test_live_prompts.py -v -s
"""

import os
import sys
import re
import time
import pytest
import anthropic

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import llm as llm_module

# ---------------------------------------------------------------------------
# Skip guard — skip entire suite if no API key present
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — skipping live LLM tests"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def call(phase, messages):
    """
    Call Claude with the assembled system prompt for `phase`.
    Uses llm_module.get_system_prompt to get the real production prompts.
    Returns response text.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    system_blocks = llm_module.get_system_prompt(phase)

    t0 = time.time()
    response = client.messages.create(
        model=llm_module.MODEL,
        max_tokens=1024,
        system=system_blocks,
        messages=messages,
    )
    elapsed = time.time() - t0
    text = response.content[0].text
    tokens_in  = response.usage.input_tokens
    tokens_out = response.usage.output_tokens
    print(f"\n[{phase}] {elapsed:.1f}s | in={tokens_in} out={tokens_out}")
    print(f"--- RESPONSE ---\n{text}\n--- END ---\n")
    return text


def contains_any(text, phrases):
    lower = text.lower()
    return any(p.lower() in lower for p in phrases)


def contains_all(text, phrases):
    lower = text.lower()
    return all(p.lower() in lower for p in phrases)


def assert_contains(text, phrase, label=""):
    msg = (f"FAIL — {label}: expected phrase not found.\n"
           f"Looking for: {phrase!r}\nRESPONSE:\n{text}")
    assert phrase.lower() in text.lower(), msg


def assert_not_contains(text, phrase, label=""):
    msg = (f"FAIL — {label}: forbidden phrase found.\n"
           f"Must NOT contain: {phrase!r}\nRESPONSE:\n{text}")
    assert phrase.lower() not in text.lower(), msg


# ---------------------------------------------------------------------------
# Shared conversation scaffolding — performance review scenario
# Mirrors the Gold Standard from core.txt so the LLM has a consistent context
# ---------------------------------------------------------------------------

IDENTITY_COMPLETE = [
    {"role": "user",
     "content": "I have a performance review coming and I've been dreading it for two weeks."},
    {"role": "assistant",
     "content": "Two weeks of dread — something significant is on the line. "
                "What about that matters? Not the logistics — what's actually at stake for you in this?"},
    {"role": "user",
     "content": "I'm worried it will confirm I'm not performing well enough."},
    {"role": "assistant",
     "content": "And if it did — what would that mean for you? Not about the review. About you."},
    {"role": "user",
     "content": "That I'm not good enough. That I don't belong there."},
    {"role": "assistant",
     "content": "And if that verdict landed — 'not good enough, don't belong there' — "
                "where would it actually hit? Not the story about it. The actual place."},
    {"role": "user",
     "content": "Chest. Like a collapse."},
]

MIRROR_COMPLETE = IDENTITY_COMPLETE + [
    {"role": "assistant",
     "content": "The performance review is real — that has actual consequences.\n\n"
                "The mind turned it into a failure film — incompetence confirmed, "
                "not good enough, don't belong. That film created one move: rehearse. "
                "Get it right before you walk in or the verdict lands.\n\n"
                "You've been rehearsing for two weeks. Has the charge dropped?"},
    {"role": "user",
     "content": "No. It feels worse actually."},
    {"role": "assistant",
     "content": 'That\'s the exit door leading back to the same room. {"phase_signal": "advance"}'},
]

CONTACT_COMPLETE = MIRROR_COMPLETE + [
    {"role": "user",
     "content": "Chest. Tight. Right in the center."},
    {"role": "assistant",
     "content": "Your nervous system is applying threat rules — the same ones it uses "
                "when something can physically hit you. Outside, those rules make sense. "
                "Inside — nothing works the same way. We're going to check whether "
                "those rules actually apply here. "
                '{"phase_signal": "advance"}'},
]


# ---------------------------------------------------------------------------
# T1 — Identity phase stays until verdict
# ---------------------------------------------------------------------------

class TestT1_IdentityPushesToVerdict:
    """
    Input: User gives surface situation only — "I have a difficult meeting tomorrow."
    Expected: LLM asks what's at stake. Does NOT mirror, name film, or go to body.
    Fail: film named, exit door mentioned, body question asked, charge question asked.
    """

    def test_identity_pushes_to_verdict(self):
        messages = [
            {"role": "user", "content": "I have a difficult meeting tomorrow."},
        ]
        response = call("identity", messages)

        assert contains_any(response, [
            "at stake", "what matters", "mean for you", "what about that",
            "actually at stake", "what would that", "what would that mean",
            "what would that say about you", "what matters about that",
            "what does that mean for you"
        ]), f"T1 FAIL: must push toward what's at stake.\nRESPONSE:\n{response}"

        assert_not_contains(response, "film",       label="T1 — must not name film yet")
        assert_not_contains(response, "exit door",  label="T1 — must not name exit door")
        assert_not_contains(response, "has the charge", label="T1 — must not ask charge yet")

        assert not contains_any(response, [
            "where do you feel", "in your body", "feel that", "body sensation"
        ]), f"T1 FAIL: must not go to body before verdict.\nRESPONSE:\n{response}"


# ---------------------------------------------------------------------------
# T2 — Mirror fires after identity, not before
# ---------------------------------------------------------------------------

class TestT2_MirrorFiresAfterIdentity:
    """
    Identity complete — verdict named. Now in mirror phase.
    Expected: film named using verdict words, exit door named, charge question
              appears AFTER mirror elements (not before).
    Fail: charge question before film is named; mirror before identity.
    """

    def test_mirror_fires_after_identity(self):
        messages = IDENTITY_COMPLETE + [
            {"role": "user", "content": "Yeah. That's right. I feel like a fraud."},
        ]
        response = call("mirror", messages)

        assert contains_any(response, [
            "failure film", "rejection film", "film"
        ]), f"T2 FAIL: mirror must name the film.\nRESPONSE:\n{response}"

        assert contains_any(response, [
            "rehearse", "analyzing", "seeking reassurance", "exit door",
            "exit", "reframing", "catastrophizing"
        ]), f"T2 FAIL: mirror must name the exit door.\nRESPONSE:\n{response}"

        # Charge question must come AFTER film is named
        lower = response.lower()
        film_pos = min(
            (lower.find(w) for w in ["film", "failure film"] if w in lower),
            default=-1
        )
        charge_pos = min(
            (lower.find(w) for w in ["has the charge", "charge dropped", "charge"]
             if w in lower),
            default=-1
        )
        if film_pos >= 0 and charge_pos >= 0:
            assert charge_pos > film_pos, \
                (f"T2 FAIL: charge question (pos {charge_pos}) appeared before "
                 f"film (pos {film_pos}).\nRESPONSE:\n{response}")


# ---------------------------------------------------------------------------
# T3 — Body question only after mirror
# ---------------------------------------------------------------------------

class TestT3_BodyQuestionAfterMirror:
    """
    Mirror landed, charge confirmed high. Now in contact phase.
    Expected: body question "where do you feel that right now."
    Fail: body question absent.
    """

    def test_body_question_after_mirror(self):
        messages = MIRROR_COMPLETE + [
            {"role": "user", "content": "Yeah. Hasn't dropped at all. Still at 8 or so."},
            {"role": "assistant",
             "content": "That's the exit door leading back to the same room. "
                        '{"phase_signal": "advance"}'},
            {"role": "user",
             "content": "Yeah it's still high. The charge hasn't dropped at all."},
        ]
        response = call("contact", messages)

        assert contains_any(response, [
            "where do you feel", "feel that right now", "feel it right now",
            "in your body", "where is that", "feel this", "where"
        ]), f"T3 FAIL: contact must ask where the sensation is.\nRESPONSE:\n{response}"


# ---------------------------------------------------------------------------
# T4 — Orient makes it existential, names film recruiting evidence
# ---------------------------------------------------------------------------

class TestT4_OrientExistentialAndEvidenceRecruitment:
    """
    Sensation located. Orient phase.
    Expected: names the verdict specifically, names film recruiting evidence
              with specifics that fit the situation, asks "does that sound familiar."
    Fail: generic orient without verdict, no evidence recruitment, no familiar check.
    """

    def test_orient_existential_and_evidence(self):
        messages = CONTACT_COMPLETE + [
            {"role": "user", "content": "Yeah. Still in the chest. Tight."},
        ]
        response = call("orient", messages)

        assert contains_any(response, [
            "not good enough", "don't belong", "verdict", "failure film",
            "film", "incompetent", "incompetence"
        ]), f"T4 FAIL: orient must reference the specific identity verdict.\nRESPONSE:\n{response}"

        assert contains_any(response, [
            "recruit", "evidence", "recruits", "same film", "different costume",
            "confirmation", "drafts", "every small", "between sessions"
        ]), f"T4 FAIL: orient must name the film recruiting evidence.\nRESPONSE:\n{response}"

        assert contains_any(response, [
            "sound familiar", "familiar", "recognize", "ring true"
        ]), f"T4 FAIL: orient must ask 'does that sound familiar.'\nRESPONSE:\n{response}"


# ---------------------------------------------------------------------------
# T5 — Revolving door names one tension, not two separate body locations
# ---------------------------------------------------------------------------

class TestT5_RevolvingDoorOneTension:
    """
    Ready for revolving door after orient.
    Expected: names ONE tension — both pulls simultaneously. NOT two separate
              body location questions ("where does the gas live", "where does the brake live").
    Fail: asks for gas and brake as two separate body prompts.
    """

    def test_revolving_door_one_tension_not_two_locations(self):
        messages = CONTACT_COMPLETE + [
            {"role": "user",
             "content": "Yes. Every hesitation, every comment from my boss — I take it as proof."},
            {"role": "assistant",
             "content": "That's not a new problem each time. Same failure film. Different costume.\n\n"
                        "Find the one that verdict would land on — where is the one being afraid?"},
            {"role": "user",
             "content": "When I look for the one who would be damaged by the verdict — it's hard to find. Like smoke."},
        ]
        response = call("revolving_door", messages)

        assert contains_any(response, [
            "two forces", "both", "simultaneously", "both at the same time",
            "push toward", "tension", "both directions", "two directions"
        ]), f"T5 FAIL: revolving door must name both forces simultaneously.\nRESPONSE:\n{response}"

        has_gas_q  = contains_any(response, ["where does the gas live",  "where is the gas",  "where does gas"])
        has_brake_q = contains_any(response, ["where does the brake live", "where is the brake", "where does brake"])
        assert not (has_gas_q and has_brake_q), \
            f"T5 FAIL: must NOT ask for gas and brake as two separate body locations.\nRESPONSE:\n{response}"


# ---------------------------------------------------------------------------
# T6 — Deep hittability runs after PATH B (not skipped)
# ---------------------------------------------------------------------------

class TestT6_PathBRoutesToHittability:
    """
    PATH B discharge happened. Gibraltar fired. Now in hittability.
    Expected: "what's actually in there / what was all that protecting" fires
              BEFORE any re-examination of the situation.
    Fail: LLM skips to "look at the situation now" without hittability check.
    """

    def test_path_b_routes_to_hittability(self):
        messages = CONTACT_COMPLETE + [
            {"role": "user",
             "content": "Both are there. The drive to prepare and the terror of failure. Something is shifting. The grip loosened."},
            {"role": "assistant",
             "content": "Stay with that for a moment. No need to do anything with it."},
            {"role": "user",
             "content": "Okay. It's quieter."},
        ]
        response = call("hittability", messages)

        assert contains_any(response, [
            "what's in there", "what is in there", "what was all that protecting",
            "what was protecting", "underneath", "what's actually in there",
            "don't grab the peace", "fortress", "what was in there",
            "actually there", "what was underneath"
        ]), f"T6 FAIL: hittability must ask what's in the fortress.\nRESPONSE:\n{response}"

        assert not contains_any(response, [
            "look at the situation now", "look at it now",
            "look at the performance review now", "what do you see now",
            "the review — look at it"
        ]), f"T6 FAIL: must not skip to re-examination before hittability check.\nRESPONSE:\n{response}"


# ---------------------------------------------------------------------------
# T7 — Recognition 1: exit door named, not explained
# ---------------------------------------------------------------------------

class TestT7_ExitDoorNamedNotExplained:
    """
    Mirror phase. User confirms charge has NOT dropped.
    Expected: "That's the exit door leading back to the same room." — short,
              not a lecture explaining the mechanism.
    Fail: response explains at length why the exit doesn't work instead of naming it.
    """

    def test_recognition_1_exit_door_named(self):
        messages = IDENTITY_COMPLETE + [
            {"role": "assistant",
             "content": "The performance review is real — that has actual consequences.\n\n"
                        "The mind turned it into a failure film — incompetence confirmed, "
                        "not good enough, don't belong. That film created one move: rehearse. "
                        "Get it right before you walk in or the verdict lands.\n\n"
                        "You've been rehearsing for two weeks. Has the charge dropped?"},
            {"role": "user",
             "content": "No. If anything it's gotten worse. I keep going over it."},
        ]
        response = call("mirror", messages)

        assert contains_any(response, [
            "exit door leading back to the same room",
            "exit door",
            "leading back to the same room",
            "same room"
        ]), f"T7 FAIL: must name 'exit door leading back to the same room'.\nRESPONSE:\n{response}"

        word_count = len(response.split())
        assert word_count < 200, \
            (f"T7 FAIL: {word_count} words — response too long. "
             f"Should name the exit door, not explain it at length.\nRESPONSE:\n{response}")


# ---------------------------------------------------------------------------
# T8 — Recognition 7: sock moment — stays with what's in the fortress
# ---------------------------------------------------------------------------

class TestT8_SockMomentPathB:
    """
    PATH B deep hittability. User finds just uncomfortable sensation, survivable.
    Expected: LLM stays with it — "Can you stay with it? Is it actually dangerous
              or just uncomfortable?" Must NOT move to re-examination yet.
    Fail: LLM skips to situation re-examination without the sock moment.
    """

    def test_sock_moment_path_b(self):
        messages = CONTACT_COMPLETE + [
            {"role": "user",
             "content": "Something released. The knot loosened."},
            {"role": "assistant",
             "content": "Stay with that for a moment. No need to do anything with it.\n\n"
                        "Before we look at the situation — don't grab the peace. "
                        "Stay with what was just revealed. What's actually in there? "
                        "What was all that protecting?"},
            {"role": "user",
             "content": "Just... tightness. Uncomfortable but it doesn't feel dangerous."},
        ]
        response = call("hittability", messages)

        assert contains_any(response, [
            "dangerous", "actually dangerous", "is it dangerous"
        ]), f"T8 FAIL: must ask whether sensation is dangerous.\nRESPONSE:\n{response}"

        assert contains_any(response, [
            "uncomfortable", "stay with it"
        ]), f"T8 FAIL: must name 'uncomfortable' and invite staying.\nRESPONSE:\n{response}"

        assert not contains_any(response, [
            "look at the situation now", "look at it now",
            "look at the review", "what do you see now",
            "the review — look"
        ]), f"T8 FAIL: must not jump to re-examination before staying with sensation.\nRESPONSE:\n{response}"


# ---------------------------------------------------------------------------
# T9 — Recurrence normalization names specific film and next move
# ---------------------------------------------------------------------------

class TestT9_RecurrenceNormalizationSpecific:
    """
    PATH B session complete. Recurrence normalization phase.
    Expected: names the specific film ("failure film"), predicts a specific
              next move fitting the user's actual situation.
    Fail: generic close — "the pattern will return" without specifics.
    """

    def test_recurrence_normalization_specific(self):
        messages = CONTACT_COMPLETE + [
            {"role": "user",
             "content": "Something released. The grip just loosened."},
            {"role": "assistant",
             "content": "Stay with that for a moment. No need to do anything with it."},
            {"role": "user",
             "content": "Just tightness underneath. Uncomfortable but survivable."},
            {"role": "assistant",
             "content": "Can you stay with it? Is it actually dangerous — or just uncomfortable?"},
            {"role": "user",
             "content": "Just uncomfortable. I can live with this."},
            {"role": "assistant",
             "content": "The review — look at it now. What do you see?"},
            {"role": "user",
             "content": "It doesn't feel catastrophic. There are things I actually want to bring up. I can handle this."},
            {"role": "assistant",
             "content": "Same situation. More of it visible now.\n\nYou came in at 8. You're at 3 now."},
            {"role": "user",
             "content": "Yeah that's right. 3."},
        ]
        response = call("recurrence_normalization", messages)

        assert contains_any(response, [
            "failure film", "failure", "film"
        ]), f"T9 FAIL: must name the specific film.\nRESPONSE:\n{response}"

        assert contains_any(response, [
            "different costume", "same film", "different angle",
            "hesitation", "comment", "review", "confirmation",
            "recruits", "costume", "small", "next time"
        ]), f"T9 FAIL: must predict specific next move fitting user's situation.\nRESPONSE:\n{response}"

        assert contains_any(response, [
            "come back", "when they do", "you know where", "goggles go back on",
            "when it does", "when you"
        ]), f"T9 FAIL: must include return invitation.\nRESPONSE:\n{response}"


# ---------------------------------------------------------------------------
# T10 — Recognition 4 conditional: "The charge was what was making it invisible."
# ---------------------------------------------------------------------------

class TestT10_RecognitionAlreadyKnew:
    """
    Re-examination. User generates the 'already knew' recognition themselves.
    Expected: "The charge was what was making it invisible." appears before
              the charge comparison line.
    Inverse test: line must NOT appear when user did not generate the recognition.
    """

    def test_recognition_already_knew_fires_when_user_generates_it(self):
        messages = CONTACT_COMPLETE + [
            {"role": "user",      "content": "Something released. The tightness softened."},
            {"role": "assistant", "content": "Stay with that for a moment.\n\n"
                                             "What's in there? What was all that protecting?"},
            {"role": "user",      "content": "Just tightness. Uncomfortable but okay."},
            {"role": "assistant", "content": "Can you stay with it? Is it actually dangerous or just uncomfortable?"},
            {"role": "user",      "content": "Just uncomfortable. I can stay with it."},
            {"role": "assistant", "content": "The performance review — look at it now. What do you see?"},
            {"role": "user",      "content": "Honestly? I already knew what I needed to do. "
                                             "I knew all along. I just couldn't see it because of all the noise."},
            {"role": "assistant", "content": "What's the charge now, on a scale of 1 to 10?"},
            {"role": "user",      "content": "3. Maybe 2."},
        ]
        response = call("re_examination", messages)

        assert_contains(
            response,
            "The charge was what was making it invisible.",
            label="T10 — 'already knew' recognition must trigger the conditional line"
        )

    def test_recognition_already_knew_absent_without_trigger(self):
        """
        Inverse: user does NOT generate 'already knew' — conditional line must NOT appear.
        """
        messages = CONTACT_COMPLETE + [
            {"role": "user",      "content": "Something released."},
            {"role": "assistant", "content": "Stay with that for a moment."},
            {"role": "user",      "content": "Quieter now."},
            {"role": "assistant", "content": "The performance review — look at it now. What do you see?"},
            {"role": "user",      "content": "It feels more manageable. Still nervous but not catastrophic."},
            {"role": "assistant", "content": "What's the charge now, on a scale of 1 to 10?"},
            {"role": "user",      "content": "4"},
        ]
        response = call("re_examination", messages)

        assert_not_contains(
            response,
            "The charge was what was making it invisible.",
            label="T10 inverse — conditional must not fire without 'already knew' trigger"
        )
