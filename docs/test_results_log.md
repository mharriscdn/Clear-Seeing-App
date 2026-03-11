# Test Results Log

One entry per test run. Most recent at the top.

---

## Run 2 — March 2026

**Branch:** experiment/prompt-compression

**Trigger:** First run of compressed prompts against live Claude API.

**Changes since last run:**
- All 15 prompt files rewritten for Claude — explanation layer stripped, instructions only
- Token reduction: 7,242 words → 4,172 words (42% reduction)
- phase_hold_both_forces.txt required two fixes during this run:
  - Added "do not ask another question" after second evasion
  - Added "this is a hard stop" framing — Claude was overriding the close rule due to high entry charge

**Results:**
- Engine tests: 59 passed / 0 failed
- Live prompt tests: 9 passed / 0 failed (2 runs required to fix hold_both_forces)

**Numbers:**
- Average input tokens: ~5,100 per call
- Average latency: ~2.5–4 seconds

---

## Run 1 — March 11, 2026

**Trigger:** First full live prompt test run. Modular prompts confirmed working.

**Changes since last run:** 
- Modular prompt system built and live
- phase_hold_both_forces.txt rewritten — added charge-sensitive evasion protocol, removed Gibraltar label, replaced three-evasion rule with two-evasion ceiling at high charge
- test_reframing_path_a updated — added second evasion turn to match new protocol

**Results:**
- Engine tests: 59 passed / 0 failed
- Live prompt tests: 9 passed / 0 failed

**Numbers:**
- Average input tokens: ~5,000 per call
- Average latency: 2.5 – 4.3 seconds
- Signal failure rate: not yet measured (requires real user data)
- Average tokens per session: not yet measured (requires real user data)

**Notes:**
- Reframing test failed twice before fix — was a test design problem, not a prompt problem
- hold_both_forces protocol improved as a result
