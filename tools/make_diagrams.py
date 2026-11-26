#!/usr/bin/env python3
"""Generate the SVG diagrams of the documentation (English and Hungarian) into docs/img/.

Source of truth for the run state graph: runner/sweep.py (execute, Runner.wait_paused, cmd_resume).
  python tools/make_diagrams.py
"""
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent.parent / "docs" / "img"

NODES = {  # state: (x, y, fill, stroke)
    "starting": (60, 190, "#e7f5ff", "#4dabf7"),
    "running": (330, 190, "#d0ebff", "#1c7ed6"),
    "paused": (330, 40, "#fff3bf", "#f08c00"),
    "stopped": (620, 190, "#e9ecef", "#868e96"),
    "done": (620, 330, "#d3f9d8", "#2f9e44"),
    "aborted": (330, 330, "#ffe3e3", "#e03131"),
}
W, H = 140, 48

# (path, dashed, label_x, label_y, anchor, label key)
EDGES = [
    ("M20,214 H58", False, 34, 205, "middle", "start"),
    ("M200,214 H328", False, 265, 205, "middle", "checks_ok"),
    ("M370,190 V90", False, 362, 143, "end", "pause"),
    ("M430,88 V188", False, 438, 143, "start", "resume"),
    ("M470,214 H618", False, 545, 205, "middle", "stop_ctrlc"),
    ("M470,64 H690 V188", False, 580, 55, "middle", "stop"),
    ("M450,238 V284 H690 V328", False, 570, 275, "middle", "all_done"),
    ("M400,238 V328", False, 392, 306, "end", "error_timeouts"),
    ("M130,238 V354 H328", False, 230, 345, "middle", "error"),
    ("M760,214 H778 V16 H100 V188", True, 215, 32, "middle", "resume_new"),
    ("M690,378 V420 H80 V240", True, 560, 412, "middle", "resume_done"),
    ("M400,378 V420", True, 240, 412, "middle", "resume_aborted"),
]

TEXT = {
    "en": {"start": "run", "checks_ok": "checks ok", "pause": "pause / GPU busy", "resume": "resume / GPU free",
           "stop_ctrlc": "stop / Ctrl+C", "stop": "stop", "all_done": "all jobs finished",
           "error_timeouts": "error / 2 timeouts", "error": "error", "resume_new": "resume (new process)",
           "resume_done": "resume --from / --redo-failed", "resume_aborted": "resume",
           "legend_solid": "same process", "legend_dashed": "resume starts a new process",
           "title": "Run states"},
    "hu": {"start": "run", "checks_ok": "ellenőrzés ok", "pause": "pause / foglalt GPU", "resume": "resume / szabad GPU",
           "stop_ctrlc": "stop / Ctrl+C", "stop": "stop", "all_done": "minden job kész",
           "error_timeouts": "hiba / 2 timeout", "error": "hiba", "resume_new": "resume (új process)",
           "resume_done": "resume --from / --redo-failed", "resume_aborted": "resume",
           "legend_solid": "ugyanaz a process", "legend_dashed": "a resume új processt indít",
           "title": "Futási állapotok"},
}


def run_states(lang):
    t = TEXT[lang]
    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 470" width="800" height="470" '
        f'role="img" aria-label="{escape(t["title"])}" font-family="Segoe UI, Arial, sans-serif">',
        '<rect width="800" height="470" fill="#ffffff"/>',
        '<defs><marker id="a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" '
        'orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#495057"/></marker></defs>',
        '<circle cx="16" cy="214" r="6" fill="#212529"/>',
    ]
    for path, dashed, lx, ly, anchor, key in EDGES:
        dash = ' stroke-dasharray="5 4"' if dashed else ""
        # the "aborted" resume edge only joins the dashed bus, so it has no arrow head of its own
        arrow = "" if key == "resume_aborted" else ' marker-end="url(#a)"'
        out.append(f'<path d="{path}" fill="none" stroke="#495057" stroke-width="1.5"{dash}{arrow}/>')
        out.append(f'<text x="{lx}" y="{ly}" text-anchor="{anchor}" font-size="12" fill="#343a40">'
                   f'{escape(t[key])}</text>')
    for name, (x, y, fill, stroke) in NODES.items():
        out.append(f'<rect x="{x}" y="{y}" width="{W}" height="{H}" rx="10" fill="{fill}" '
                   f'stroke="{stroke}" stroke-width="2"/>')
        out.append(f'<text x="{x + W / 2}" y="{y + H / 2 + 5}" text-anchor="middle" font-size="15" '
                   f'font-weight="600" font-family="Consolas, monospace" fill="#212529">{name}</text>')
    out += [
        '<path d="M60,450 H100" stroke="#495057" stroke-width="1.5"/>',
        f'<text x="108" y="454" font-size="12" fill="#495057">{escape(t["legend_solid"])}</text>',
        '<path d="M300,450 H340" stroke="#495057" stroke-width="1.5" stroke-dasharray="5 4"/>',
        f'<text x="348" y="454" font-size="12" fill="#495057">{escape(t["legend_dashed"])}</text>',
        "</svg>",
    ]
    return "\n".join(out) + "\n"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for lang, suffix in (("en", ""), ("hu", ".hu")):
        p = OUT / f"run_states{suffix}.svg"
        p.write_text(run_states(lang), encoding="utf-8")
        print("written", p)


if __name__ == "__main__":
    main()
