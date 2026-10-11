"""LAB / MOCK leakage check for markdown deliverables (LL5, critic fix 11). Owner: LAB-B.

Rule: a line that is part of a markdown TABLE must not contain "LAB:" or "MOCK" unless the table sits
under a heading whose text contains "Hands-on lab" (case-insensitive). A table counts as "under" such a
heading when that heading is the nearest heading or any ancestor heading (so "## Hands-on lab" >
"### C1 results" > table is allowed). Pass ``nearest_only=True`` for the stricter reading in which only the
nearest heading counts. Prose lines and fenced code blocks are not checked. Text before the first
heading is NOT in a Hands-on lab section.

The markers are matched case-sensitively, as in the provenance tags ("LAB:c1:...", "MOCK:jev").

Usage (later phases):
    from jevlab.leakage import assert_no_lab_or_mock_in
    assert_no_lab_or_mock_in("STUDY.md")
    # or: python -m jevlab.leakage STUDY.md   (exit code 1 on leakage)
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

MARKERS = ("LAB:", "MOCK")
ALLOWED_HEADING = "hands-on lab"

_ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_DELIM = re.compile(r"^ {0,3}\|?[ \t]*:?-+:?[ \t]*(\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")


@dataclass(frozen=True)
class Leak:
    line_no: int
    heading: str
    marker: str
    text: str

    def __str__(self) -> str:
        return f"line {self.line_no} (under heading {self.heading!r}): {self.marker!r} in table row: {self.text.strip()}"


def _is_table_row(line: str) -> bool:
    return "|" in line and line.strip() != ""


def _n_cells(line: str) -> int:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return len(re.split(r"(?<!\\)\|", s))


def find_leaks(markdown: str, nearest_only: bool = False) -> list[Leak]:
    lines = markdown.splitlines()
    leaks: list[Leak] = []
    stack: list[tuple[int, str]] = []  # (level, heading text)
    fence: str | None = None
    in_table = False
    prev_plain: str | None = None  # previous non-table, non-blank paragraph line (for setext headings)

    def allowed() -> bool:
        heads = stack[-1:] if nearest_only else stack
        return any(ALLOWED_HEADING in h.lower() for _, h in heads)

    def push(level: int, text: str) -> None:
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, text.strip()))

    for i, line in enumerate(lines):
        no = i + 1
        m = _FENCE.match(line)
        if fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
            continue
        if m:
            fence, in_table, prev_plain = m.group(1), False, None
            continue
        if not line.strip():
            in_table, prev_plain = False, None
            continue
        h = _ATX.match(line)
        if h:
            push(len(h.group(1)), h.group(2) or "")
            in_table, prev_plain = False, None
            continue
        # table start: a row with '|' followed by a delimiter row
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if (not in_table and _is_table_row(line) and _DELIM.match(nxt) and "-" in nxt
                and _n_cells(line) == _n_cells(nxt)):  # GFM: header and delimiter cell counts must match
            in_table = True
        if not in_table and _SETEXT.match(line) and prev_plain is not None:
            push(1 if line.strip()[0] == "=" else 2, prev_plain)
            prev_plain = None
            continue
        if in_table or line.lstrip().startswith("|"):
            if not allowed():
                for mk in MARKERS:
                    if mk in line:
                        leaks.append(Leak(no, stack[-1][1] if stack else "<no heading>", mk, line))
                        break
            prev_plain = None
            continue
        prev_plain = line
    return leaks


def assert_no_lab_or_mock_in(path: str | Path, nearest_only: bool = False) -> None:
    """Raise AssertionError listing every LAB:/MOCK value found in a table outside a 'Hands-on lab' section."""
    p = Path(path)
    leaks = find_leaks(p.read_text(encoding="utf-8"), nearest_only=nearest_only)
    if leaks:
        raise AssertionError(f"{p}: {len(leaks)} LAB/MOCK value(s) in tables outside a 'Hands-on lab' section:\n"
                             + "\n".join(f"  {lk}" for lk in leaks))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    strict = "--nearest-only" in args
    paths = [a for a in args if a != "--nearest-only"] or ["STUDY.md"]
    bad = 0
    for p in paths:
        try:
            assert_no_lab_or_mock_in(p, nearest_only=strict)
            print(f"OK   {p}: no LAB/MOCK values in headline tables")
        except AssertionError as e:
            bad += 1
            print(f"FAIL {e}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
