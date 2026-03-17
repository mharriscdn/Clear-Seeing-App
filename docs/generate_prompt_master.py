"""
Reads docs/prompt_manifest.json and services/prompts/ to produce
docs/prompt_master.docx — the authoritative single-file view of every prompt.

Run directly:  python docs/generate_prompt_master.py
Also called on every app startup (see app.py).
"""

import json
import os

from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "prompt_manifest.json")
PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "services", "prompts")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "prompt_master.docx")

EXPLANATIONS = {
    "core.txt": (
        "The always-on coaching brain. Every rule, failure mode, metaphor, and path "
        "definition. Loaded every session, every turn."
    ),
    "signal_instruction.txt": (
        "The telemetry layer. Forces Claude to append a machine-readable JSON signal "
        "so the phase engine knows what to do next. Loaded every session, every turn."
    ),
    "phase_mirror.txt": (
        "First contact. Reflects the user's situation back in their own words, gets "
        "the charge number, names the escape move, and shows why it doesn't work — "
        "it's just another hand on the revolving door."
    ),
    "phase_examinability.txt": (
        "Checks if the user can observe the sensation without being consumed by the "
        "story. Gate before any investigation begins."
    ),
    "phase_activation_check.txt": (
        "Confirms the sensation feels like protection or bracing. Rules out neutral "
        "or physical sensation before escalating."
    ),
    "phase_recovery.txt": (
        "Conditional detour for dysregulation. Four sub-routes matched to four "
        "failure modes. Returns to main spine once examinability is restored."
    ),
    "phase_orient.txt": (
        "Narrows the search space. Tells the user what they're looking for without "
        "telling them what they'll find. Evasion tracking starts here."
    ),
    "phase_pointer.txt": (
        "The investigation tool. One of ten questions the user checks in the body, "
        "not the mind."
    ),
    "phase_revolving_door.txt": (
        "Gets the user to feel the push itself — the urge to escape — before "
        "examining what they're running from."
    ),
    "phase_hold_both_forces.txt": (
        "The fork. User holds both the urge to escape and what they're escaping from "
        "simultaneously. PATH A, B, or C determined here."
    ),
    "phase_courage_gate.txt": (
        "PATH C only. Gives permission to remain at the edge. "
        "Hesitation here is not evasion."
    ),
    "phase_hittability.txt": (
        "PATH C only. Physical verification. Where in the body would the damage land? "
        "Tests whether the predicted harm actually arrives."
    ),
    "phase_integration.txt": (
        "PATH C only. Three beats acknowledging what just happened. "
        "No teaching. No explanation. Then stop."
    ),
    "phase_gibraltar.txt": (
        "PATH B only. Charge dissolved before hittability could run. "
        "One settling sentence. Do not test what is no longer live."
    ),
    "phase_re_examination.txt": (
        "The return. User looks at their original problem through whatever aperture "
        "the session produced. Charge delta reported here."
    ),
    "phase_recurrence_normalization.txt": (
        "The close. One or two sentences matched to the path. "
        "No questions. Session ends here unconditionally."
    ),
}


def generate():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    doc = Document()

    # --- Document title ---
    title = doc.add_heading("CLEAR SEEING GUIDE — Prompt Master Document", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # --- Auto-generated note ---
    note = doc.add_paragraph(
        "Auto-generated. Do not edit manually. "
        "Run generate_prompt_master.py to update."
    )
    note.runs[0].italic = True
    note.runs[0].font.color.rgb = RGBColor(0x88, 0x88, 0x88)

    doc.add_paragraph()

    for position, filename in enumerate(manifest, start=1):
        prompt_path = os.path.join(PROMPTS_DIR, filename)
        with open(prompt_path, "r", encoding="utf-8") as f:
            content = f.read().strip()

        explanation = EXPLANATIONS.get(filename, "")

        # --- Section heading ---
        heading = doc.add_heading(f"#{position} — {filename}", level=1)
        heading.runs[0].font.color.rgb = RGBColor(0x1A, 0x1A, 0x1A)

        # --- Explanation line ---
        if explanation:
            exp_para = doc.add_paragraph(explanation)
            exp_para.runs[0].italic = True
            exp_para.runs[0].font.size = Pt(10)
            exp_para.runs[0].font.color.rgb = RGBColor(0x55, 0x55, 0x55)

        # --- Prompt body (monospace, preserve line breaks) ---
        body = doc.add_paragraph()
        body.paragraph_format.space_before = Pt(6)
        run = body.add_run(content)
        run.font.name = "Courier New"
        run.font.size = Pt(9)

        # --- Divider ---
        div = doc.add_paragraph("—" * 60)
        div.runs[0].font.color.rgb = RGBColor(0xCC, 0xCC, 0xCC)
        div.runs[0].font.size = Pt(8)

        doc.add_paragraph()

    doc.save(OUTPUT_PATH)
    print(f"prompt_master.docx written — {len(manifest)} prompts.")


if __name__ == "__main__":
    generate()
