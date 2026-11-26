#!/usr/bin/env python3
"""Export the project documents (docs/roadmap.md, docs/architecture.md) to formatted PDFs next to them.

More folders can be added in the optional, untracked file tools/export_docs.local.json; every Markdown
document in them is exported too:  {"extra_folders": ["my-notes"]}

Stdlib only; the PDF is printed by headless Microsoft Edge. Supports the Markdown subset used by these
documents: headings, paragraphs, pipe tables, bullet lists (with checkboxes), numbered lists, fenced
code blocks, images, **bold**, `code`, links.

  python tools/export_docs.py                      # all documents
  python tools/export_docs.py architecture         # one document
  python tools/export_docs.py --html-dir DIR [--no-pdf]
"""
import argparse
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DOCS = ("roadmap", "architecture")
LOCAL_SETTINGS = ROOT / "tools" / "export_docs.local.json"
LANGS = {"": "en", ".hu": "hu"}  # file suffix -> language; English is primary
STATES = {"done": "done", "partial": "partial", "in progress": "running", "open": "open",
          "kész": "done", "részben": "partial", "folyamatban": "running", "nyitott": "open"}
STATUS_HEADERS = ("status", "állapot")
NOWRAP_HEADERS = ("Source", "Forrás")
FOOTER = {"en": "Generated: {stamp} · source: {path}", "hu": "Generálva: {stamp} · forrás: {path}"}

CSS = """
@page { size: A4; margin: 14mm 13mm 16mm 13mm; }
* { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font: 9.5pt/1.45 "Segoe UI", Arial, sans-serif; color: #1f2933; margin: 0; }
h1 { font-size: 19pt; margin: 0 0 6px; color: #102a43; border-bottom: 3px solid #2f6fed; padding-bottom: 6px; }
h2 { font-size: 12.5pt; margin: 16px 0 6px; color: #1d4ed8; break-after: avoid; }
h3 { font-size: 10.5pt; margin: 10px 0 4px; color: #243b53; break-after: avoid; }
p { margin: 4px 0 8px; }
table { width: 100%; border-collapse: collapse; margin: 4px 0 10px; font-size: 8.8pt; }
th { background: #1e3a5f; color: #fff; text-align: left; padding: 5px 7px; }
td { border-bottom: 1px solid #d9e2ec; padding: 4.5px 7px; vertical-align: top; }
tr { break-inside: avoid; }
tbody tr:nth-child(even) td { background: #f4f7fb; }
td.num { width: 26px; text-align: center; font-weight: 600; color: #486581; }
td.nw { white-space: nowrap; }
pre { background: #f4f7fb; border: 1px solid #d9e2ec; border-radius: 5px; padding: 8px 10px; margin: 4px 0 10px; white-space: pre-wrap; break-inside: avoid; }
pre code { background: none; padding: 0; }
figure { margin: 6px 0 10px; break-inside: avoid; border: 1px solid #d9e2ec; border-radius: 6px; padding: 6px; }
figure svg, figure img { display: block; max-width: 100%; height: auto; margin: 0 auto; }
ul, ol { margin: 3px 0 8px; padding-left: 18px; }
li { margin: 2px 0; }
li.check { list-style: none; margin-left: -16px; }
code { font: 8.4pt Consolas, monospace; background: #eef2f7; border-radius: 3px; padding: 0 3px; }
.badge { display: inline-block; border-radius: 9px; padding: 0 7px; font-weight: 600; font-size: 8.2pt; white-space: nowrap; }
.done { background: #d3f9d8; color: #1b5e20; }
.partial { background: #fff3bf; color: #7a5200; }
.running { background: #d0ebff; color: #0b4f8a; }
.open { background: #e9ecef; color: #495057; }
.foot { margin-top: 18px; color: #829ab1; font-size: 7.8pt; border-top: 1px solid #d9e2ec; padding-top: 4px; }
"""


def inline(text):
    parts = re.split(r"(`[^`]*`)", text)
    out = []
    for p in parts:
        if len(p) > 1 and p.startswith("`") and p.endswith("`"):
            out.append(f"<code>{html.escape(p[1:-1])}</code>")
            continue
        p = html.escape(p, quote=False)
        p = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", p)
        p = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', p)
        out.append(p)
    s = "".join(out)
    # bold spans that contain code
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)


def cell(text, header):
    if header.strip().lower() in STATUS_HEADERS:
        for word, cls in STATES.items():
            m = re.match(rf"{word}\b(.*)", text)
            if m:
                return f'<span class="badge {cls}">{word}</span>{inline(m.group(1))}'
    return inline(text)


def split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def convert(md, source, lang):
    lines = md.splitlines()
    title = next((ln[2:].strip() for ln in lines if ln.startswith("# ")), source.stem)
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1
        elif m := re.match(r"!\[([^\]]*)\]\(([^)\s]+)\)\s*$", ln):
            image = (source.parent / m.group(2)).resolve()
            if image.suffix.lower() == ".svg":  # inline, so the HTML works from any folder
                body = re.sub(r"^<\?xml[^>]*>\s*", "", image.read_text(encoding="utf-8"))
            else:
                body = f'<img src="{image.as_uri()}" alt="{html.escape(m.group(1))}">'
            out.append(f"<figure>{body}</figure>")
            i += 1
        elif ln.startswith("```"):
            code = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            out.append(f"<pre><code>{html.escape(chr(10).join(code))}</code></pre>")
        elif re.match(r"\d+\.\s", ln):
            out.append("<ol>")
            while i < len(lines) and re.match(r"\d+\.\s", lines[i]):
                item = re.sub(r"^\d+\.\s+", "", lines[i])
                i += 1
                while i < len(lines) and lines[i].startswith("  ") and lines[i].strip():
                    item += " " + lines[i].strip()
                    i += 1
                out.append(f"<li>{inline(item)}</li>")
            out.append("</ol>")
        elif m := re.match(r"(#{1,4})\s+(.*)", ln):
            n = len(m.group(1))
            out.append(f"<h{n}>{inline(m.group(2))}</h{n}>")
            i += 1
        elif ln.startswith("|") and i + 1 < len(lines) and re.match(r"\|[\s:|-]+\|?\s*$", lines[i + 1]):
            head = split_row(ln)
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(h)}</th>" for h in head)
                       + "</tr></thead><tbody>")
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                row = split_row(lines[i])
                tds = []
                for k, c in enumerate(row):
                    h = head[k] if k < len(head) else ""
                    cls = ' class="num"' if h == "#" else ' class="nw"' if h in NOWRAP_HEADERS else ""
                    tds.append(f"<td{cls}>{cell(c, h)}</td>")
                out.append("<tr>" + "".join(tds) + "</tr>")
                i += 1
            out.append("</tbody></table>")
        elif ln.startswith("- "):
            out.append("<ul>")
            while i < len(lines) and lines[i].startswith("- "):
                item = lines[i][2:]
                i += 1
                while i < len(lines) and lines[i].startswith("  ") and lines[i].strip():
                    item += " " + lines[i].strip()
                    i += 1
                if m := re.match(r"\[([ xX])\]\s+(.*)", item):
                    box = "&#9745;" if m.group(1).lower() == "x" else "&#9744;"
                    out.append(f'<li class="check">{box} {inline(m.group(2))}</li>')
                else:
                    out.append(f"<li>{inline(item)}</li>")
            out.append("</ul>")
        else:
            para = [ln.strip()]
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(r"(#|\||- |```|!\[|\d+\.\s)", lines[i]):
                para.append(lines[i].strip())
                i += 1
            out.append(f"<p>{inline(' '.join(para))}</p>")
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    foot = FOOTER[lang].format(stamp=stamp, path=source.relative_to(ROOT).as_posix())
    return (f"<!doctype html><html lang='{lang}'><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
            f"<style>{CSS}</style></head><body>{''.join(out)}<div class='foot'>{foot}</div></body></html>")


def find_edge():
    for var in ("ProgramFiles(x86)", "ProgramFiles"):
        p = Path(os.environ.get(var, "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
        if p.is_file():
            return p
    raise SystemExit("Microsoft Edge not found")


def extra_folders():
    if not LOCAL_SETTINGS.is_file():
        return []
    folders = json.loads(LOCAL_SETTINGS.read_text(encoding="utf-8")).get("extra_folders", [])
    for folder in folders:
        if ROOT not in (ROOT / folder).resolve().parents:
            raise SystemExit(f"{LOCAL_SETTINGS.name}: folder must be inside the project: {folder}")
    return folders


def documents():
    """Document name -> folder."""
    found = {name: "docs" for name in PUBLIC_DOCS}
    for folder in extra_folders():
        for md in sorted((ROOT / folder).glob("*.md")):
            if md.stem.endswith(".hu"):
                continue
            if md.stem in found:
                raise SystemExit(f"duplicate document name '{md.stem}' in {folder} and {found[md.stem]}")
            found[md.stem] = folder
    return found


def export(name, folder, lang, html_dir, make_pdf):
    """name includes the language suffix, e.g. 'roadmap' or 'roadmap.hu'."""
    source, target = ROOT / folder / f"{name}.md", ROOT / folder / f"{name}.pdf"
    doc = convert(source.read_text(encoding="utf-8"), source, lang)
    html_path = html_dir / f"lmbench_{name}.html"
    html_path.write_text(doc, encoding="utf-8")
    if not make_pdf:
        print("HTML:", html_path)
        return
    tmp_pdf = target.with_suffix(".tmp.pdf")
    try:
        tmp_pdf.unlink(missing_ok=True)
    except PermissionError:
        raise SystemExit(f"{tmp_pdf} is open in a viewer; close it to export {name}")
    profile = Path(tempfile.gettempdir()) / "lmbench_edge_profile"
    subprocess.run([str(find_edge()), "--headless=new", "--disable-gpu", f"--user-data-dir={profile}",
                    "--no-pdf-header-footer", f"--print-to-pdf={tmp_pdf}", html_path.resolve().as_uri()],
                   check=True, timeout=90, capture_output=True)
    if not tmp_pdf.is_file() or tmp_pdf.stat().st_size < 1000:
        raise SystemExit("PDF was not produced")
    try:
        os.replace(tmp_pdf, target)
    except PermissionError:
        raise SystemExit(f"cannot overwrite {target} (open in a viewer?); new file kept at {tmp_pdf}")
    print(f"Written: {target} ({target.stat().st_size} bytes)")


def main():
    ap = argparse.ArgumentParser()
    known = documents()
    ap.add_argument("docs", nargs="*", help=f"documents to export (default: all of {', '.join(known)})")
    ap.add_argument("--html-dir", help="keep the intermediate HTML in this folder")
    ap.add_argument("--no-pdf", action="store_true")
    a = ap.parse_args()
    unknown = [d for d in a.docs if d not in known]
    if unknown:
        ap.error(f"unknown document(s): {unknown}")
    html_dir = Path(a.html_dir) if a.html_dir else Path(tempfile.gettempdir())
    failed = []
    for doc_name in a.docs or known:
        for suffix, lang in LANGS.items():
            try:
                export(doc_name + suffix, known[doc_name], lang, html_dir, not a.no_pdf)
            except SystemExit as e:  # e.g. one PDF is open in a viewer: still export the others
                failed.append(str(e))
    for message in failed:
        print(message, file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
