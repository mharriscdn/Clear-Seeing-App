"""
Billing service — thin wrapper around stripe_webhooks for now.

TODO Phase 2: tank_remaining deduction logic, plan enforcement.
"""
import os
import stripe_webhooks


PRICE_ID_INTRO = os.environ.get("STRIPE_PRICE_ID_INTRO")
PRICE_ID_STANDARD = os.environ.get("STRIPE_PRICE_ID_STANDARD")


def get_checkout_url(user_email, plan, success_url, cancel_url):
    """
    Returns a Stripe Checkout URL for the given plan.
    plan: 'intro' or 'standard'
    """
    if plan == "intro":
        price_id = PRICE_ID_INTRO
    else:
        price_id = PRICE_ID_STANDARD

    if not price_id:
        raise ValueError(f"Price ID for plan '{plan}' is not configured")

    session = stripe_webhooks.create_checkout_session(user_email, price_id, success_url, cancel_url)
    return session.url


def get_portal_url(user_email, return_url):
    """Returns a Stripe Customer Portal URL."""
    portal = stripe_webhooks.create_portal_session(user_email, return_url)
    if not portal:
        return None
    return portal.url
