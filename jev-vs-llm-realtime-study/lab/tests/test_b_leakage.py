"""Tests for jevlab.leakage.assert_no_lab_or_mock_in (LL5). Owner: LAB-B.

Later phases run the same helper against STUDY.md:
    python -m jevlab.leakage ../STUDY.md
"""
from __future__ import annotations

from pathlib import Path

import pytest

from jevlab.leakage import assert_no_lab_or_mock_in, find_leaks

STUDY = Path(__file__).resolve().parents[2] / "STUDY.md"


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "doc.md"
    p.write_text(text)
    return p


def test_headline_table_with_lab_fails(tmp_path):
    p = _write(tmp_path, "# Results\n\n| arch | acc |\n|---|---|\n| C1a | 0.91 (LAB:c1:tfidf:fp32:linux-cpu-4vcpu) |\n")
    with pytest.raises(AssertionError, match="LAB:"):
        assert_no_lab_or_mock_in(p)


def test_headline_table_with_mock_fails(tmp_path):
    p = _write(tmp_path, "## Comparator ladder\n\nname | p95\n--- | ---\nJ1 | 12 ms MOCK:jev\n")
    leaks = find_leaks(p.read_text())
    assert len(leaks) == 1 and leaks[0].marker == "MOCK" and leaks[0].line_no == 5
    with pytest.raises(AssertionError):
        assert_no_lab_or_mock_in(p)


def test_hands_on_lab_section_allowed_including_subsections(tmp_path):
    md = ("# Study\n\n## Hands-on lab (illustrative only)\n\n| run | acc |\n|---|---|\n| c1 | LAB:c1:x |\n\n"
          "### C1 sweep\n\n| N | acc |\n|---|---|\n| 50 | LAB:c1:y |\n| stub | MOCK:jev |\n")
    p = _write(tmp_path, md)
    assert_no_lab_or_mock_in(p)  # allowed: ancestor heading contains "Hands-on lab"
    with pytest.raises(AssertionError):
        assert_no_lab_or_mock_in(p, nearest_only=True)  # strict reading: nearest heading only


def test_leaving_the_lab_section_restores_the_check(tmp_path):
    md = ("## Hands-on lab\n\n| a |\n|---|\n| LAB:ok |\n\n## Recommendation\n\n| a | b |\n|---|---|\n| x | MOCK |\n")
    leaks = find_leaks(md)
    assert [lk.heading for lk in leaks] == ["Recommendation"]


def test_prose_and_code_blocks_are_not_tables(tmp_path):
    md = ("# Results\n\nThe LAB: tag and MOCK values appear only in prose here.\n\n"
          "```\n| x | LAB:c1 |\n|---|---|\n| MOCK | y |\n```\n")
    assert find_leaks(md) == []


def test_table_before_any_heading_is_checked():
    assert len(find_leaks("| a | b |\n|---|---|\n| LAB:x | 1 |\n")) == 1


def test_setext_heading_and_case(tmp_path):
    md = "Hands-on LAB results\n====================\n\n| a | b |\n|---|---|\n| LAB:x | 1 |\n"
    assert find_leaks(md) == []  # heading match is case-insensitive
    assert find_leaks("# R\n\n| a | b |\n|---|---|\n| lab: mock | 1 |\n") == []  # markers are case-sensitive


@pytest.mark.skipif(not STUDY.exists(), reason="STUDY.md not written yet (Phase 4)")
def test_study_md_has_no_lab_or_mock_in_headline_tables():
    assert_no_lab_or_mock_in(STUDY)
