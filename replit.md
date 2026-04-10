# Clear Being Guide

## Overview
A minimal conversational AI coaching app built with Python Flask. The conversation is the product — no gamification, no wellness UI. Users log in via Replit Auth, start sessions, and converse with Claude.

## Architecture

**Backend:** Python Flask (`app.py`) — thin routes only, no business logic in routes.
**Database:** PostgreSQL via `psycopg2` (Replit-provided `DATABASE_URL`).
**AI:** Anthropic Claude (claude-sonnet-4-6) via server-side `llm.py` only.
**Auth:** Replit Auth (X-Replit-User headers).
**Billing:** Stripe (checkout + webhooks + customer portal).

## Key Files
- `app.py` — Flask routes
- `db.py` — All DB queries
- `auth.py` — Replit Auth decorator
- `llm.py` — `get_system_prompt()` and `call_claude()` ONLY
- `stripe_webhooks.py` — Stripe webhook and portal logic
- `system_prompt.txt` — Claude system prompt (not exposed to client)
- `services/` — Business logic layer (Phase 2 coaching logic goes here)

## Database Tables
- `users` — id, email, created_at, subscription_status, tank_remaining
- `sessions` — id, user_id, created_at, updated_at, conversation_phase, perceptual_state, opening_problem
- `messages` — id, session_id, role, content, created_at, token_count, model
- `session_outcomes` — id, session_id, ending_type, re_examination_ran, re_examination_response, field_widening_detected (empty in Phase 1)

## Required Secrets
- `ANTHROPIC_API_KEY`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_ID_INTRO`
- `STRIPE_PRICE_ID_STANDARD`
- `SESSION_SECRET` (already set)
- `DATABASE_URL` (already set by Replit)

## Run Command
```
python app.py
```
Runs on port 5000.

## Phase
Phase 1 complete. Phase 2 will add coaching logic in `services/`.
