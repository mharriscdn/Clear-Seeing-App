# Test Results Log

One entry per test run. Most recent at the top.

---

## Run 3 — March 11, 2026

**Trigger:** Signal fallback feature implemented.

**Changes since last run:**
- `set_signal_retry` added to `db.py` — sets boolean flag on sessions table when Claude misses a signal
- `get_system_prompt` updated to accept `signal_retry=False` — when True, appends next phase module under `--- NEXT PHASE (for reference) ---` header
- `TRANSITION_MAP` added to `llm.py` — defines advance path through all 14 phases
- `call_claude` passes `signal_retry` flag through to `get_system_prompt`
- `chat_service.py` reads flag from session, passes to `call_claude`, resets after every turn

**Results:**
- Engine tests: 68 passed / 0 failed
- Live prompt tests: 9 passed / 0 failed

**Notes:**
- All previous tests still passing
- 9 new tests added since Run 1 (68 total vs 59)

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
