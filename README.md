# Clear Seeing Guide

A minimal conversational AI coaching app. The conversation is the product.

## Environment Variables

Set these as secrets in your Replit project (Secrets tab):

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key for Claude |
| `STRIPE_SECRET_KEY` | Stripe secret key (from Stripe dashboard) |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret |
| `STRIPE_PRICE_ID_INTRO` | Stripe Price ID for the Intro plan |
| `STRIPE_PRICE_ID_STANDARD` | Stripe Price ID for the Standard plan |
| `SESSION_SECRET` | Flask session secret (already set by Replit) |
| `DATABASE_URL` | PostgreSQL connection string (provided by Replit) |

## Stripe Setup

1. Create your products and prices in the Stripe dashboard.
2. Set `STRIPE_PRICE_ID_INTRO` and `STRIPE_PRICE_ID_STANDARD` to the corresponding Price IDs.
3. Create a webhook endpoint pointing to `https://your-domain/api/stripe/webhook` with these events:
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
4. Copy the webhook signing secret into `STRIPE_WEBHOOK_SECRET`.

## Deploy

1. Click **Deploy** in the Replit toolbar.
2. The app runs via `python app.py` on port 5000.
3. Update your Stripe webhook URL to the production domain after deploying.

## Code Structure

```
app.py               — Flask routes (thin)
db.py                — Database connection and queries
auth.py              — Replit Auth integration
llm.py               — Claude API (get_system_prompt, call_claude only)
stripe_webhooks.py   — Stripe webhook handler
system_prompt.txt    — System prompt (never exposed to client)
services/
  chat_service.py    — Chat logic (Phase 2 coaching logic goes here)
  session_service.py — Session lifecycle
  billing_service.py — Billing helpers
static/
  style.css
  app.js
templates/
  index.html
```

## Phase 1 Completion Checklist

- [x] User can log in and start a session
- [x] First user message stored as `opening_problem` on session record
- [x] Messages saved with role, content, timestamp, model, token_count
- [x] Stripe webhook updates `subscription_status` on user record
