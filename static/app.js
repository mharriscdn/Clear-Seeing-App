let currentSessionId = null;

// Load user info on page load
async function init() {
    try {
        const res = await fetch("/api/me");
        if (res.status === 401) {
            window.location.href = "/auth/replit_auth";
            return;
        }
        if (!res.ok) return;
        const me = await res.json();
        const tankEl = document.getElementById("tank-value");
        if (tankEl) {
            tankEl.textContent = me.capacity_remaining != null ? me.capacity_remaining : "—";
        }
    } catch (e) {
        console.error("Failed to load user info", e);
    }
}

async function startSession() {
    const btn = document.getElementById("start-btn");
    btn.disabled = true;
    btn.textContent = "Starting...";

    try {
        const res = await fetch("/api/session/new", { method: "POST" });

        if (res.status === 401) {
            window.location.href = "/auth/replit_auth";
            return;
        }

        const data = await res.json();

        if (!res.ok || !data.session_id) {
            alert("Could not start session. Please try again.");
            btn.disabled = false;
            btn.textContent = "Begin session";
            return;
        }

        currentSessionId = data.session_id;

        document.getElementById("session-start").style.display = "none";
        document.getElementById("chat-area").style.display = "flex";

        // Render the fixed opening message
        renderMessage({ role: "assistant", content: "What\u2019s in your central view right now?" });

    } catch (e) {
        console.error("startSession error:", e);
        alert("Could not start session.");
        btn.disabled = false;
        btn.textContent = "Begin session";
    }
}

function stripSignal(content) {
    return content.replace(/\{[^{}]*"phase_signal"[^{}]*\}/g, "").trim();
}

function renderMessage(msg) {
    const transcript = document.getElementById("transcript");
    const el = document.createElement("div");
    el.className = `message ${msg.role}`;
    el.textContent = msg.role === "assistant" ? stripSignal(msg.content) : msg.content;
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

    renderMessage({ role: "user", content: text });

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: currentSessionId, user_message: text }),
        });

        const data = await res.json();

        if (!res.ok) {
            renderMessage({ role: "assistant", content: data.error || "Something went wrong. Please try again." });
        } else {
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
