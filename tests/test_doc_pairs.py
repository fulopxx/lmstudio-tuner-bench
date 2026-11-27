"""The English and Hungarian versions of every document must have the same structure.

Compared per pair: heading levels, table sizes, list items, requirement and decision ids, status icons, images and
dates. A Hungarian line must not start with an ordinal ("23. feladat"), because Markdown would read it as a numbered
list. Also checks that the PDF export keeps requirement state icons and turns task statuses into badges.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import export_docs  # noqa: E402

ICONS = "✅🧪🟡⚪🔵"
ORDINAL_LINE = re.compile(r"^\s*\d+\. [a-záéíóöőúüű]")


def pairs():
    """README, docs/ and the extra folders of the untracked export settings (the same documents as the PDF export;
    without that file only the public documents are checked)."""
    found = [(ROOT / "README.md", ROOT / "README.hu.md")]
    for folder in ["docs", *export_docs.extra_folders()]:
        for en in sorted((ROOT / folder).glob("*.md")):
            if not en.name.endswith(".hu.md"):
                found.append((en, en.with_name(en.name[:-3] + ".hu.md")))
    return found


def structure(text):
    lines = text.split("\n")
    tables, rows = [], 0
    for line in lines + [""]:
        if line.startswith("|"):
            rows += 1
        elif rows:
            tables.append(rows)
            rows = 0
    return {
        "heading levels": [len(ln) - len(ln.lstrip("#")) for ln in lines if re.match(r"#{1,6} ", ln)],
        "table rows": tables,
        "table columns": [ln.count("|") for ln in lines if ln.startswith("|---")],
        "list items": sum(1 for ln in lines if re.match(r"\s*(- |\d+\. )", ln)),
        "ids": sorted(set(re.findall(r"\b(?:FA|SD|TS|CR)-\d\d\b|\bH\d\b", text))),
        "icons": "".join(c for c in text if c in ICONS),
        "images": len(re.findall(r"!\[", text)),
        "dates": sorted(re.findall(r"\b20\d\d-\d\d-\d\d\b", text)),
    }


class DocumentPairTest(unittest.TestCase):
    def test_every_public_document_has_a_hungarian_pair(self):
        for en, hu in pairs():
            self.assertTrue(hu.exists(), f"{hu.name} is missing")

    def test_pairs_have_the_same_structure(self):
        for en, hu in pairs():
            a = structure(en.read_text(encoding="utf-8"))
            b = structure(hu.read_text(encoding="utf-8"))
            for key in a:
                with self.subTest(document=en.name, aspect=key):
                    self.assertEqual(a[key], b[key], f"{en.name} and {hu.name} differ in {key}")

    def test_no_hungarian_line_starts_with_an_ordinal(self):
        for _, hu in pairs():
            for n, line in enumerate(hu.read_text(encoding="utf-8").split("\n"), 1):
                with self.subTest(document=hu.name, line=n):
                    self.assertIsNone(ORDINAL_LINE.match(line), f"{hu.name}:{n} would render as a list: {line[:60]}")


class ExportStatusCellTest(unittest.TestCase):
    def test_task_status_becomes_a_badge(self):
        self.assertIn('class="badge done"', export_docs.cell("✅ kész (2026-11-27)", "Állapot"))
        self.assertIn('class="badge partial"', export_docs.cell("🟡 partial (x)", "Status"))

    def test_requirement_state_keeps_its_icon(self):
        self.assertEqual(export_docs.cell("✅", "Állapot"), "✅")
        self.assertTrue(export_docs.cell("🧪 offline only", "Állapot").startswith("🧪"))


if __name__ == "__main__":
    unittest.main()
