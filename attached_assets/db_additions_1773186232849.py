# ---------------------------------------------------------------------------
# ADD THESE TO db.py
# ---------------------------------------------------------------------------

# 1. In init_db(), add these two ALTER TABLE statements alongside the existing ones:

    cur.execute(
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS phase_signal TEXT"
    )
    cur.execute(
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS old_phase TEXT"
    )
    cur.execute(
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS new_phase TEXT"
    )

# 2. Add this new function at the bottom of the Phase Engine additions section:

def log_signal_transition(message_id, phase_signal, old_phase, new_phase):
    """Records the signal and phase transition for every assistant message."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """UPDATE messages
           SET phase_signal = %s, old_phase = %s, new_phase = %s
           WHERE id = %s""",
        (phase_signal, old_phase, new_phase, message_id),
    )
    conn.commit()
    cur.close()
    conn.close()
