import os
import stripe
import db
from datetime import datetime, timedelta

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")


def _get_price_plan(price_id):
    """
    Return plan config for the given Stripe Price ID, or None if unrecognised.
    Price IDs come from environment variables so no code change is needed when
    prices are updated in Stripe.
    """
    if not price_id:
        return None
    price_map = {
        os.environ.get("STRIPE_PRICE_ID_INTRO"):    {"units": 5000,  "set_reset": True},
        os.environ.get("STRIPE_PRICE_ID_STANDARD"): {"units": 10000, "set_reset": True},
    }
    # Drop entries where the env var is not set (key would be None)
    price_map = {k: v for k, v in price_map.items() if k}
    return price_map.get(price_id)


def handle_webhook(payload, sig_header):
    """
    Processes Stripe webhook events.
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
        customer_id = data.get("customer")
        status = data.get("status")
        # Map Stripe subscription statuses to our internal statuses
        internal_status = "active" if status == "active" else status
        _set_status_by_customer_id(customer_id, internal_status)

    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer")
        _set_status_by_customer_id(customer_id, "canceled")

    elif event_type == "invoice.paid":
        customer_id = data.get("customer")
        if customer_id:
            _set_status_by_customer_id(customer_id, "active")

    elif event_type == "checkout.session.completed":
        customer_id = data.get("customer")
        session_id = data.get("id")

        # Retrieve the session with line_items expanded to read the Price ID
        price_id = None
        try:
            expanded = stripe.checkout.Session.retrieve(
                session_id, expand=["line_items"]
            )
            items = expanded.line_items.data if expanded.line_items else []
            if items:
                price_id = items[0].price.id
        except Exception as e:
            print(f"[stripe_webhooks] Failed to expand session {session_id}: {e}")

        plan = _get_price_plan(price_id)
        if plan:
            reset_date = (
                (datetime.utcnow() + timedelta(days=30)).date()
                if plan["set_reset"] else None
            )
            _add_capacity_for_customer(customer_id, plan["units"], reset_date)

        _set_status_by_customer_id(customer_id, "active")

    return {"received": True}, 200


def _set_status_by_customer_id(stripe_customer_id, status):
    """
    Updates subscription_status by stripe_customer_id stored in DB.
    Falls back to Stripe email lookup for users whose stripe_customer_id
    was not stored yet.
    """
    if not stripe_customer_id:
        return
    try:
        # Preferred: look up directly by stripe_customer_id in our DB
        user = db.get_user_by_stripe_customer_id(stripe_customer_id)
        if user:
            db.update_subscription_by_stripe_customer(stripe_customer_id, status)
            return
        # Fallback: fetch email from Stripe and match by email
        customer = stripe.Customer.retrieve(stripe_customer_id)
        email = customer.get("email")
        if email:
            db.update_user_subscription(email, status)
            print(
                f"[stripe_webhooks] fallback email lookup for "
                f"customer={stripe_customer_id} email={email} status={status}"
            )
    except Exception as e:
        print(f"[stripe_webhooks] Failed to set status for customer {stripe_customer_id}: {e}")


def _update_user_by_customer(customer_id, status):
    """Legacy wrapper — kept for compatibility. Delegates to _set_status_by_customer_id."""
    _set_status_by_customer_id(customer_id, status)


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
    """
    Legacy signature — used by billing_service.
    Creates a Checkout session using customer_email (no stored customer ID).
    """
    session = stripe.checkout.Session.create(
        customer_email=user_email,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return session


def create_paywall_checkout(user, price_id, success_url, cancel_url):
    """
    Paywall flow — gets or creates a Stripe Customer, stores the customer ID
    on the user record, then creates and returns a Checkout session.
    """
    stripe_customer_id = user.get("stripe_customer_id")

    if not stripe_customer_id:
        customer = stripe.Customer.create(email=user["email"])
        stripe_customer_id = customer.id
        db.update_stripe_customer_id(user["id"], stripe_customer_id)

    session = stripe.checkout.Session.create(
        customer=stripe_customer_id,
        payment_method_types=["card"],
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return session


def create_portal_session(user_email, return_url):
    """Creates a Stripe Customer Portal session for managing billing."""
    customers = stripe.Customer.list(email=user_email, limit=1)
    if not customers.data:
        return None
    customer_id = customers.data[0].id
    portal = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return portal
