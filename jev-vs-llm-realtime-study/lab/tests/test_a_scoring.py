"""Tokenizer-aware option scoring on FAKE logprob payloads (LL3 pitfalls)."""
import math

import pytest

from jevlab import scoring as S

LABELS = ["bill_balance", "bill_due", "out_of_scope"]
CODES = {"bill_balance": "A", "bill_due": "B", "out_of_scope": "C"}


def entry(token, lp, tops):
    return {"token": token, "logprob": lp, "top_logprobs": [{"token": t, "logprob": l} for t, l in tops]}


def test_leading_space_and_case_variants_are_merged():
    tops = [("A", -1.2), (" A", -1.5), ("a", -2.0), ("B", -1.0), (" b", -2.5), ("\nC", -3.0), ("A)", -4.0)]
    r = S.score_from_logprobs([entry("A", -1.2, tops)], CODES, LABELS, threshold=0.0)
    ma = math.exp(-1.2) + math.exp(-1.5) + math.exp(-2.0) + math.exp(-4.0)
    mb = math.exp(-1.0) + math.exp(-2.5)
    mc = math.exp(-3.0)
    z = ma + mb + mc
    assert r.probs["bill_balance"] == pytest.approx(ma / z)
    assert r.probs["bill_due"] == pytest.approx(mb / z)
    assert r.captured_mass == pytest.approx(z)
    assert r.label == "bill_balance"  # merged A beats the single best token B


def test_normalize_token_variants():
    for t in ["A", " A", "a", " a", "\nA", "A)", "(A", '"A', "A."]:
        assert S.normalize_token(t) == "A"
    assert S.normalize_token("Answer") == "ANSWER"


def test_codes_are_single_token_and_prefix_free_with_tokenizer():
    # Toy vocab: "C" exists only without a leading space -> C must be skipped.
    vocab = ["A", " A", "B", " B", "C", "D", " D", "E", " E"]
    cm = S.assign_codes(LABELS, S.DictTokenizer(vocab))
    assert cm.verified and cm.usable
    assert cm.codes == {"bill_balance": "A", "bill_due": "B", "out_of_scope": "D"}


def test_too_many_options_for_single_token_codes_is_reported():
    cm = S.assign_codes([f"l{i}" for i in range(5)], S.DictTokenizer(["A", " A", "B", " B"]))
    assert not cm.usable and "full-sequence" in cm.problems[0]


def test_multi_token_label_sequence_logprob_in_json_mode():
    # {"label": "out_of_scope"} where the label is three tokens
    content = [
        entry('{"', -0.01, []), entry("label", -0.0, []), entry('":', -0.0, []), entry(' "', -0.02, []),
        entry("out", -0.5, []), entry("_of", -0.1, []), entry("_scope", -0.2, []), entry('"}', -0.3, []),
    ]
    lp, n = S.value_span_logprob(content, "out_of_scope")
    assert n == 3 and lp == pytest.approx(-0.8)


def test_full_sequence_handles_shared_prefix_labels():
    # bill_balance and bill_due share the token "bill"; full-sequence scores whole options
    p = S.full_sequence_probs({"bill_balance": -1.0, "bill_due": -2.0, "out_of_scope": -5.0})
    assert max(p, key=p.get) == "bill_balance" and sum(p.values()) == pytest.approx(1.0)
    pn = S.full_sequence_probs({"a": -2.0, "b": -1.5}, {"a": 4, "b": 1}, length_norm=True)
    assert pn["a"] > pn["b"]  # -0.5/token beats -1.5/token


def test_think_prefix_is_skipped():
    content = [entry("<think>", -0.1, []), entry("hmm", -0.1, []), entry("</think>", -0.1, []), entry("\n\n", -0.1, []),
               entry("B", -0.2, [("B", -0.2), ("A", -1.9)])]
    r = S.score_from_logprobs(content, CODES, LABELS, threshold=0.0)
    assert r.position == 4 and r.label == "bill_due" and r.how == "after_think"


def test_unclosed_think_block_gives_no_label():
    content = [entry("<think>", -0.1, []), entry("let me", -0.1, [])]
    r = S.score_from_logprobs(content, CODES, LABELS)
    assert r.label is None and r.fallback_needed and r.how == "unclosed_think_block"


def test_json_wrapped_label_position():
    content = [entry('{"', -0.01, []), entry("label", -0.01, []), entry('":', -0.01, []), entry(' "', -0.01, []),
               entry("C", -0.1, [("C", -0.1), ("A", -2.5), ("B", -3.5)]), entry('"}', -0.01, [])]
    r = S.score_from_logprobs(content, CODES, LABELS, threshold=0.0)
    assert r.position == 4 and r.how == "json" and r.label == "out_of_scope"


def test_plain_answer_prefix_and_leading_whitespace():
    content = [entry("Answer", -0.3, []), entry(":", -0.1, []), entry(" B", -0.2, [(" B", -0.2), (" A", -2.0)])]
    r = S.score_from_logprobs(content, CODES, LABELS, threshold=0.0)
    assert r.position == 2 and r.label == "bill_due"


def test_topk_truncation_low_captured_mass_triggers_fallback():
    tops = [("The", -0.3), ("A", -2.0), ("B", -2.5)]
    r = S.score_from_logprobs([entry("The", -0.3, tops)] , CODES, LABELS)
    assert r.how == "plain"
    # label position is token 0 ("The" is not a code), mass on codes ~0.22 < 0.9
    assert r.captured_mass == pytest.approx(math.exp(-2.0) + math.exp(-2.5))
    assert r.fallback_needed and "captured_mass" in r.fallback_reason
    # the missing code C gets a floor, distribution still sums to 1
    assert sum(r.probs.values()) == pytest.approx(1.0) and r.probs["out_of_scope"] > 0


def test_empty_logprobs_is_flagged_not_scored():
    r = S.score_from_logprobs([], CODES, LABELS)
    assert r.probs is None and r.fallback_needed and r.how == "empty_logprobs"


def test_normalise_ollama_native_and_lmstudio_shapes():
    native = [{"token": "A", "logprob": -0.1, "bytes": [65], "top_logprobs": [{"token": "A", "logprob": -0.1, "bytes": [65]}]}]
    assert S.normalise_logprob_content(native)[0]["top_logprobs"][0]["token"] == "A"
    assert S.normalise_logprob_content({"content": native})[0]["token"] == "A"
    assert S.normalise_logprob_content(None) == []


def test_top1_distribution():
    d = S.top1_distribution("b", 0.7, ["a", "b", "c"])
    assert d == pytest.approx({"a": 0.15, "b": 0.7, "c": 0.15})


def test_mlx_lm_shape_raw_bpe_unsorted_first_position():
    # mlx-lm 0.32.0: top list from argpartition (unsorted), raw BPE pieces, entry token = first of list
    raw = {"content": [{"id": 1, "token": "ĠB", "logprob": -2.0, "top_logprobs": [
        {"id": 1, "token": "ĠB", "logprob": -2.0}, {"id": 2, "token": "A", "logprob": -0.1}, {"id": 3, "token": "Ġa", "logprob": -3.0}]}]}
    content = S.normalise_logprob_content(raw, token_format="bpe_raw")
    assert content[0]["top_logprobs"][0]["token"] == "A"  # sorted by logprob
    assert content[0]["top_logprobs"][2]["token"] == " a"  # 'Ġa' -> ' a'
    r = S.score_from_logprobs(content, CODES, LABELS, threshold=0.0, label_position="first")
    assert r.position == 0 and r.label == "bill_balance"
    assert r.captured_mass == pytest.approx(math.exp(-0.1) + math.exp(-3.0) + math.exp(-2.0))
