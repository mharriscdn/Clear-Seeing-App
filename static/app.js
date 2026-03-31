let currentSessionId = null;
let currentPhase = null;
let holdTimerId = null;
let selectedRole = null;
let roleInjected = false;

// ---------------------------------------------------------------------------
// Hold-both-forces timer
// ---------------------------------------------------------------------------

function startHoldTimer() {
    clearHoldTimer();
    holdTimerId = setTimeout(sendCheckin, 10000);
}

function clearHoldTimer() {
    if (holdTimerId !== null) {
        clearTimeout(holdTimerId);
        holdTimerId = null;
    }
}

function afterAssistantMessage() {
    if (currentPhase === "hold_both_forces") {
        startHoldTimer();
    } else {
        clearHoldTimer();
    }
}

async function sendCheckin() {
    holdTimerId = null;
    if (!currentSessionId) return;
    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: currentSessionId, user_message: "__checkin__" }),
        });
        const data = await res.json();
        if (res.ok) {
            if (data.current_phase) currentPhase = data.current_phase;
            renderTranscript(data.transcript);
            afterAssistantMessage();
        }
    } catch (e) {
        console.error("sendCheckin error:", e);
    }
}

// ---------------------------------------------------------------------------
// Init / user info
// ---------------------------------------------------------------------------

async function init() {
    try {
        const res = await fetch("/api/me");
        if (res.status === 401) {
            window.location.href = "/login";
            return;
        }
        if (!res.ok) return;
        const me = await res.json();
        const tankEl = document.getElementById("tank-value");
        if (tankEl) {
            tankEl.textContent = me.capacity_remaining != null ? me.capacity_remaining : "\u2014";
        }
    } catch (e) {
        console.error("Failed to load user info", e);
    }
}

// ---------------------------------------------------------------------------
// Session start
// ---------------------------------------------------------------------------

async function startSession() {
    const btn = document.getElementById("start-btn");
    btn.disabled = true;
    btn.textContent = "Starting\u2026";

    try {
        const res = await fetch("/api/session/new", { method: "POST" });

        if (res.status === 401) {
            window.location.href = "/login";
            return;
        }

        const data = await res.json();

        if (!res.ok || !data.session_id) {
            alert("Could not start session. Please try again.");
            btn.disabled = false;
            btn.textContent = "BEGIN SESSION";
            return;
        }

        currentSessionId = data.session_id;
        currentPhase = "mirror";

        document.getElementById("landing-screen").style.display = "none";
        document.getElementById("orientation-screen").style.display = "flex";
        document.getElementById("orientation-input").focus();

    } catch (e) {
        console.error("startSession error:", e);
        alert("Could not start session.");
        btn.disabled = false;
        btn.textContent = "BEGIN SESSION";
    }
}

// ---------------------------------------------------------------------------
// Card selection
// ---------------------------------------------------------------------------

function selectCard(roleName, cardEl) {
    selectedRole = roleName;
    document.querySelectorAll('.role-card').forEach(function(c) {
        c.classList.remove('selected');
    });
    cardEl.classList.add('selected');
    beginWithRole();
}

function beginWithRole() {
    if (!selectedRole || !currentSessionId) return;

    document.body.classList.add('session-started');
    document.getElementById('orientation-screen').style.display = 'none';
    document.getElementById('chat-area').style.display = 'flex';

    const intro = document.getElementById('chat-intro');
    const el = document.createElement('div');
    el.className = 'message assistant';
    el.textContent = "Good. You\u2019re playing " + selectedRole + ".\n\nGive me a situation \u2014 a specific moment in time where this character\u2019s fear could show up.\n\nSomething like: \u2018I\u2019m about to walk into my boss\u2019s office for a performance review and I\u2019m not sure I have the answers he\u2019s going to want.\u2019\n\nDoesn\u2019t have to be real. But the more specific the moment, the better the test runs.\n\nWhat\u2019s the situation?";
    intro.appendChild(el);

    const userInput = document.getElementById('user-input');
    if (userInput) userInput.focus();
}

// ---------------------------------------------------------------------------
// Orientation / first message
// ---------------------------------------------------------------------------

function handleOrientationKey(e) {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendOrientationMessage();
    }
}

async function sendOrientationMessage() {
    document.getElementById('privacy-note').style.display = 'none';
    const input = document.getElementById("orientation-input");
    const btn = document.getElementById("orientation-send-btn");
    const text = input.value.trim();

    if (!text || !currentSessionId) return;

    document.body.classList.add('session-started');
    input.disabled = true;
    btn.disabled = true;

    document.getElementById("orientation-screen").style.display = "none";
    document.getElementById("chat-area").style.display = "flex";

    showSituationAnchor(text);
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
            if (data.current_phase) currentPhase = data.current_phase;
            renderTranscript(data.transcript);
            afterAssistantMessage();
        }
    } catch (e) {
        console.error("sendOrientationMessage error:", e);
        renderMessage({ role: "assistant", content: "[Connection error]" });
    } finally {
        const userInput = document.getElementById("user-input");
        const sendBtn = document.getElementById("send-btn");
        if (userInput) userInput.disabled = false;
        if (sendBtn) sendBtn.disabled = false;
        if (userInput) userInput.focus();
    }
}

// ---------------------------------------------------------------------------
// Rendering helpers
// ---------------------------------------------------------------------------

function showSituationAnchor(text) {
    const el = document.getElementById("situation-anchor");
    if (!el) return;
    el.innerHTML =
        '<span class="anchor-label">SITUATION</span>' +
        '<span class="anchor-text">\u201C' + text + '\u201D</span>';
    el.style.display = "flex";
}

function stripSignal(content) {
    // Handles simple {"phase_signal": "x"} and nested {"phase_signal": "x", "session_meta": {...}}
    return content.replace(/\{(?:[^{}]|\{[^{}]*\})*"phase_signal"(?:[^{}]|\{[^{}]*\})*\}/g, "").trim();
}

function renderMessage(msg) {
    const transcript = document.getElementById("transcript");
    const el = document.createElement("div");
    el.className = `message ${msg.role}`;
    let content = msg.role === "assistant" ? stripSignal(msg.content) : msg.content;
    if (msg.role === "user") {
        content = content.replace(/^\[ROLE:[^\]]*\]\s*/, '');
    }
    el.textContent = content;
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

// ---------------------------------------------------------------------------
// Chat input
// ---------------------------------------------------------------------------

function handleKey(e) {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
    // Reset hold-both-forces timer on any keydown
    if (currentPhase === "hold_both_forces") {
        clearHoldTimer();
    }
}

async function sendMessage() {
    document.getElementById('privacy-note').style.display = 'none';
    const input = document.getElementById("user-input");
    const btn = document.getElementById("send-btn");
    const text = input.value.trim();

    if (!text || !currentSessionId) return;

    clearHoldTimer();

    input.value = "";
    input.disabled = true;
    btn.disabled = true;

    let textToSend = text;
    if (!roleInjected && selectedRole) {
        textToSend = '[ROLE: ' + selectedRole + '] ' + text;
        roleInjected = true;
        showSituationAnchor(text);
    }

    renderMessage({ role: "user", content: text });

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: currentSessionId, user_message: textToSend }),
        });

        const data = await res.json();

        if (!res.ok) {
            renderMessage({ role: "assistant", content: data.error || "Something went wrong. Please try again." });
        } else {
            if (data.current_phase) currentPhase = data.current_phase;
            renderTranscript(data.transcript);
            afterAssistantMessage();
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

// ---------------------------------------------------------------------------
// Billing
// ---------------------------------------------------------------------------

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
