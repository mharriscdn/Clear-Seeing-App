let currentSessionId = null;

async function init() {
    let me;
    try {
        const res = await fetch("/api/me");
        if (res.status === 401) {
            // Not authenticated — auth wall stays visible
            return;
        }
        me = await res.json();
    } catch (e) {
        console.error("Failed to reach /api/me", e);
        return;
    }

    // Show app, hide auth wall
    document.getElementById("auth-wall").style.display = "none";
    document.getElementById("app").style.display = "flex";

    // Populate tank display
    const tankEl = document.getElementById("tank-value");
    if (tankEl) {
        tankEl.textContent = me.tank_remaining != null ? me.tank_remaining : "—";
    }

    // Show the "Begin session" button
    document.getElementById("session-start").style.display = "flex";
}

async function startSession() {
    const btn = document.getElementById("start-btn");
    btn.disabled = true;
    btn.textContent = "Starting...";

    try {
        const res = await fetch("/api/session/new", { method: "POST" });
        const data = await res.json();

        if (!res.ok || !data.session_id) {
            alert("Could not start session. Please try again.");
            btn.disabled = false;
            btn.textContent = "Begin session";
            return;
        }

        currentSessionId = data.session_id;

        // Swap UI
        document.getElementById("session-start").style.display = "none";
        document.getElementById("chat-area").style.display = "flex";

        // Load the initial assistant message
        loadTranscript();

    } catch (e) {
        console.error("startSession error:", e);
        alert("Could not start session.");
        btn.disabled = false;
        btn.textContent = "Begin session";
    }
}

async function loadTranscript() {
    // After creating a session, the opening message is already saved.
    // We re-use the chat response to get the transcript.
    // For the initial load, just fetch transcript by sending a dummy refresh.
    // Simpler: just render the opening message directly.
    renderMessage({ role: "assistant", content: "What\u2019s in your central view right now?" });
}

function renderMessage(msg) {
    const transcript = document.getElementById("transcript");
    const el = document.createElement("div");
    el.className = `message ${msg.role}`;
    el.textContent = msg.content;
    transcript.appendChild(el);
    transcript.scrollTop = transcript.scrollHeight;
}

function renderTranscript(messages) {
    const transcript = document.getElementById("transcript");
    transcript.innerHTML = "";
    for (const msg of messages) {
        renderMessage(msg);
    }
}

function handleKey(e) {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

async function sendMessage() {
    const input = document.getElementById("user-input");
    const btn = document.getElementById("send-btn");
    const text = input.value.trim();

    if (!text || !currentSessionId) return;

    input.value = "";
    input.disabled = true;
    btn.disabled = true;

    // Optimistically render the user message
    renderMessage({ role: "user", content: text });

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: currentSessionId, user_message: text }),
        });

        const data = await res.json();

        if (!res.ok) {
            renderMessage({ role: "assistant", content: "[Error: " + (data.error || "unknown") + "]" });
        } else {
            // Render full transcript to stay in sync
            renderTranscript(data.transcript);
        }
    } catch (e) {
        console.error("sendMessage error:", e);
        renderMessage({ role: "assistant", content: "[Connection error]" });
    } finally {
        input.disabled = false;
        btn.disabled = false;
        input.focus();
    }
}

async function manageBilling(e) {
    e.preventDefault();
    try {
        const res = await fetch("/api/billing/portal", { method: "POST" });
        const data = await res.json();
        if (data.url) {
            window.open(data.url, "_blank");
        } else {
            // No Stripe customer yet — send to checkout
            const checkoutRes = await fetch("/api/billing/checkout", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ plan: "standard" }),
            });
            const checkoutData = await checkoutRes.json();
            if (checkoutData.url) {
                window.open(checkoutData.url, "_blank");
            } else {
                alert("Billing is not yet configured.");
            }
        }
    } catch (e) {
        console.error("manageBilling error:", e);
        alert("Could not open billing.");
    }
}

init();
