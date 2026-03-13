import os
import stripe
import db
from datetime import datetime, timedelta

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

# Capacity granted per plan (in cents → capacity units)
_CHECKOUT_AMOUNT_MAP = {
    499:  {"units": 4990, "set_reset": True},   # month one  ($4.99)
    999:  {"units": 9990, "set_reset": True},   # subscription ($9.99)
    500:  {"units": 5000, "set_reset": False},  # top-up ($5.00) — no expiry change
}


def handle_webhook(payload, sig_header):
    """
    Processes Stripe webhook events and updates subscription_status on the user record.
    Returns (response_dict, http_status_code).
    """
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except ValueError:
        return {"error": "Invalid payload"}, 400
    except stripe.error.SignatureVerificationError:
        return {"error": "Invalid signature"}, 400

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type in ("customer.subscription.created", "customer.subscription.updated"):
        status = data.get("status")
        customer_id = data.get("customer")
        _update_user_by_customer(customer_id, status)

    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer")
        _update_user_by_customer(customer_id, "inactive")

    elif event_type == "checkout.session.completed":
        customer_id = data.get("customer")
        amount_total = data.get("amount_total")

        plan = _CHECKOUT_AMOUNT_MAP.get(amount_total)
        if plan:
            reset_date = (
                (datetime.utcnow() + timedelta(days=30)).date()
                if plan["set_reset"] else None
            )
            _add_capacity_for_customer(customer_id, plan["units"], reset_date)
            _update_user_by_customer(customer_id, "active")
        else:
            print(
                f"[stripe_webhooks] Unknown amount_total={amount_total} on "
                f"checkout.session.completed — no capacity change made"
            )
            _update_user_by_customer(customer_id, "active")

    return {"received": True}, 200


def _update_user_by_customer(customer_id, status):
    """Looks up the Stripe customer email and updates the user record."""
    try:
        customer = stripe.Customer.retrieve(customer_id)
        email = customer.get("email")
        if email:
            db.update_user_subscription(email, status)
    except Exception as e:
        # Log but don't crash — webhook must return 200
        print(f"[stripe_webhooks] Failed to update user for customer {customer_id}: {e}")


def _add_capacity_for_customer(customer_id, units, reset_date):
    """Looks up the Stripe customer email and adds capacity units."""
    try:
        customer = stripe.Customer.retrieve(customer_id)
        email = customer.get("email")
        if email:
            db.add_capacity_by_email(email, units, set_reset_date=reset_date)
            print(
                f"[stripe_webhooks] Added {units} capacity units to {email} "
                f"(reset_date={reset_date})"
            )
    except Exception as e:
        print(f"[stripe_webhooks] Failed to add capacity for customer {customer_id}: {e}")


def create_checkout_session(user_email, price_id, success_url, cancel_url):
    """Creates a Stripe Checkout session for a subscription."""
    session = stripe.checkout.Session.create(
        customer_email=user_email,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return session


def create_portal_session(user_email, return_url):
    """Creates a Stripe Customer Portal session for managing billing."""
    # Find customer by email
    customers = stripe.Customer.list(email=user_email, limit=1)
    if not customers.data:
        return None

    customer_id = customers.data[0].id
    portal = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return portal
