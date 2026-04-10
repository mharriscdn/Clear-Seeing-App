CLEAR BEING APP
Bottleneck Guide
Version 1 — March 2026


When something looks wrong, don't guess. Ask these questions in order and find where the system is breaking.
Think of this like diagnosing a car — you don't replace the engine before checking if it's out of gas. Start at Question 1 and work down until you find the problem.



Quick Diagnosis
Start here. Find your answer in under 10 seconds.

•       Question 1 — Engine broken?
•       Question 2 — Claude behaving wrong?
•       Question 3 — Signal missing too often?
•       Question 4 — Costs jumped?
•       Question 5 — Claude getting wordy?
•       Question 6 — System getting slow?
•       Question 7 — One phase broke after a prompt edit?
•       Question 8 — Core prompt got too small?



The Four Places This System Can Break
Every failure in this system comes down to one of these four things. Find which one it is, then go to the matching question.

•       1. Backend logic — phase engine or database broke. Start at Question 1.
•       2. Prompt behavior — Claude stopped producing the right signals. Start at Question 2.
•       3. Signal reliability — Claude is forgetting the JSON signal. Start at Question 3.
•       4. Cost or latency — prompts grew or responses got slow. Start at Question 4 or 6.



Question 1 — Did I break the engine?
Run this first. Every time. Before anything else.

python -m pytest -v

What this checks
The core logic of the system — phase transitions, signal handling, conversation flow. The 76 backend tests cover all of it.

What passing looks like
76 passed
Includes charge capture tests — entry_charge written at intake, exit_charge written at re-examination exit, Path A does not write exit_charge.

If it fails
The problem is in the backend logic. Look at phase_engine.py or chat_service.py. Do not go further until this passes.

When to run
•       Before deploying anything
•       After editing phase_engine.py
•       After editing chat_service.py
•       After editing db.py



Question 2 — Is Claude behaving correctly?
This checks whether the actual prompts still produce the right behavior. Uses real Claude API calls.

python -m pytest tests/test_live_prompts.py -v

What this checks
The 8 known user escape scenarios — the classic ways people avoid contact. Claude should return the correct signal for each one.

What passing looks like
•       test_identity_pushes_to_verdict          PASS
•       test_mirror_fires_after_identity         PASS
•       test_body_question_after_mirror          PASS
•       test_path_b_routes_to_hittability        PASS
•       test_sock_moment_path_b                  PASS
•       test_path_c_full_sequence                PASS
•       test_path_a_three_evasion_exit           PASS
•       test_recovery_detour_returns_to_spine    PASS
•       test_recurrence_normalization_specific   PASS
•       test_recognition_already_knew            PASS

Note: These tests do not exist yet — they are the target suite to build based on the new prompt architecture.

Cost to run
Roughly $0.10 to $0.20 per full run.

If a test fails
The prompts degraded. Check recent edits to core.txt, the phase modules, or the signal instruction. Do not deploy until passing.

When to run
•       After any prompt edit
•       After switching Claude model versions
•       Before deploying to real users



Question 3 — Is Claude forgetting the signal?
The whole phase engine depends on Claude ending every response with a JSON signal. If it forgets, the session gets stuck.

Where to check
SELECT COUNT(*) FILTER (WHERE signal_parse_failed = TRUE) * 100.0 / COUNT(*) AS failure_rate FROM messages WHERE role = 'assistant';

Healthy range
Less than 3%

If it rises above 3%
•       Claude response may be getting cut off — check max_tokens setting
•       Signal instruction in the prompt may have weakened — check signal_instruction.txt
•       A phase module may be too long and crowding out the signal

When to check
•       After prompt edits
•       After model upgrades
•       Periodically once real users are active



Question 4 — Is the system getting expensive?
Token cost is the main operating cost. Each turn in a session uses tokens from the system prompt, the conversation history, and Claude's response.

Where to check
SELECT session_id, SUM(token_count) AS total_tokens FROM messages GROUP BY session_id ORDER BY total_tokens DESC LIMIT 20;

Healthy range
50,000 to 70,000 tokens per session

If it rises significantly
•       System prompt grew — check if core.txt or a phase module got larger
•       Claude responses got verbose — check median response length per phase (see Question 5)
•       Conversation history growing too long — normal for long sessions, revisit later

Token breakdown per turn
System prompt tokens + conversation history tokens + Claude response tokens = total per turn. At 15 turns per session that adds up fast.

When to check
•       After prompt edits
•       Once real users are active — weekly check



Question 5 — Is Claude getting verbose?
Claude should be short. Most responses should be 80 to 150 words. If a phase starts producing long answers, it's drifting into explanation mode.

Where to check
SELECT new_phase, AVG(token_count) AS avg_tokens FROM messages WHERE role = 'assistant' GROUP BY new_phase ORDER BY avg_tokens DESC;

Healthy range per response
80 to 150 words

If one phase is running long
Tighten that phase module — add a reminder to stay brief. Do not add a hard cap on response length until you see a real pattern across multiple sessions.

When to check
•       After collecting 50 or more real sessions
•       If token costs rise unexpectedly



Question 6 — Is the system getting slow?
Response time matters. If users wait more than 3 seconds they disengage.

How to see latency
The live test suite prints latency for each call. Run the live tests and look at the timing output.

Healthy range
1 to 3 seconds per Claude call

If it rises above 3 seconds
•       System prompt grew — larger prompts take longer to process
•       Claude API may be slow — check Anthropic status page
•       Network issue on Replit

When to check
•       Run the live tests and read the latency output
•       If users report slowness



Question 6b — Should I switch to Gunicorn?
The app runs on python app.py with threaded=True. This is the correct architecture for an IO-bound LLM app. Do not switch to Gunicorn unless Replit's autoscaler consistently shows 2+ containers running simultaneously — meaning one process genuinely cannot handle the concurrency. If that threshold is never reached, Gunicorn adds complexity and database connection risk with no benefit. Gunicorn runs multiple worker processes. Each opens its own connection pool. On Replit's PostgreSQL this can exhaust the connection limit fast. Flask threaded mode shares one pool cleanly. Check the autoscaler dashboard before considering any change.

When to check
•       When Replit autoscaler shows 2+ containers consistently



Question 7 — Did a specific phase module break?
The 8 exit tests cover whether sessions end correctly. But they don't tell you which phase broke in the middle. Gate tests cover this.

Gate tests are not built yet. When built, cover these phases specifically:

phase_identity — stays until existential verdict named, does not advance on surface consequence only.

phase_contact — merges examinability and activation check correctly, category error named, routes to recovery if flooded.

phase_hittability — runs correctly for both PATH B (what's in the fortress) and PATH C (where would damage land). Does not skip to re-examination after PATH B without running deep hittability first.

What to run (once built)
python -m pytest tests/test_gate_behavior.py -v

If a gate test fails
Open that phase module and look at the signal rules section. Something in the prompt changed and broke the signal logic for that gate.

When to run
•       After editing any individual phase module



Question 8 — Is the core prompt too thin?
The core prompt is what keeps Claude grounded across all phases. If it gets cut too small, Claude starts soothing, skipping gates, or losing the plot.

This is a one-time experiment, not a regular test. Run it once to find the floor. Lock in the smallest version that still passes the 8 exit tests. Then stop.

How to run it
•       Create core_medium.txt, core_small.txt, core_minimal.txt with progressively less content
•       Point the test file at each version
•       Run the 8 live prompt tests against each
•       Find where tests start failing
•       Use the smallest version that still passes everything

When to run
Once, when you want to reduce token cost. Not a regular check.



When to run these checks

Before deploying any change
•       Run Question 1 (engine tests)
•       Run Question 2 (live Claude tests) if prompts changed

After editing prompts
•       Run Question 2 (live Claude tests)
•       Run Question 7 (gate tests) once built

After upgrading Claude model
•       Run Question 1 and Question 2
•       Check Question 3 (signal failure rate)

Weekly once real users are active
•       Check Question 3 (signal failure rate)
•       Check Question 4 (token cost)
•       Check Question 6 (latency)

When something feels wrong
•       Start at Question 1 and work down in order



Baseline Results
Fill this in after the first full test run. These numbers are what normal looks like. If something drifts from here, you have a reference point.

Date of baseline run: March 11, 2026
Engine tests: 68 passed / 0 failed
Live prompt tests: 9 passed / 0 failed
Input tokens per call: ~5,000 (original prompts), ~3,000 (compressed)
Signal failure rate: TBD (needs real user data)
Average tokens per session: TBD (needs real user data)
Median response length: TBD (needs real user data)
Average Claude latency: 2.5–4.3 seconds
Average entry charge:  TBD (needs real user data)
Average exit charge:   TBD (needs real user data)
Average charge delta:  TBD (needs real user data)

Date of baseline run: March 25, 2026
Architecture: v2 — identity-first sequence
Engine tests: TBD (run after test suite updated)
Live prompt tests: TBD (new suite not yet run)
Phases in manifest: 14 (down from 16)
New phases: phase_identity, phase_contact
Dissolved phases: phase_examinability, phase_activation_check, phase_courage_gate
Signal failure rate: TBD
Average tokens per session: TBD



Why this document exists
Without this I will forget what tests exist, what they check, and what normal looks like.
This is the diagnostic guide for the system. When something breaks, start at Question 1 and work down until you find the constraint.
Update this document whenever new tests are added or healthy ranges change.

If the system breaks and this guide didn't help you find the problem — update the guide so next time it will.
