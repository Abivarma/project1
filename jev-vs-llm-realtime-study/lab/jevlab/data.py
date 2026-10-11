"""Public labelled data for the Local Lab (owner: LAB-A).

load_task(name, n_intents=15, seed=7, per_class=None) -> Task

Tasks
-----
"clinc150" (DEFAULT)
    CLINC150 ("clinc/clinc_oos", config "plus", CC-BY-3.0). The default 15 intents are
    exactly CLINC's *banking* domain, plus CLINC's own out-of-scope class (renamed
    "out_of_scope"). In-scope and out-of-scope utterances therefore come from the same
    crowdsourcing process, so the OOS class cannot be spotted by style alone.
    n_intents < 15: seeded subset of the banking domain.
    15 < n_intents <= 30: banking + seeded subset of the credit_cards domain.
    n_intents > 30: banking + credit_cards + seeded intents from other domains
    (descriptions for those are auto-generated from the intent name).
    Splits follow CLINC's own splits: train <- CLINC train, calibration <- CLINC
    validation, test <- CLINC test (seeded sampling within each). No item can leak
    across our splits.

"banking77"
    PolyAI Banking77 (CC-BY-4.0). The canonical "PolyAI/banking77" repo is a loading
    script (no parquet), and loading scripts are not run here, so the parquet mirror
    "legacy-datasets/banking77" (same CC-BY-4.0 data, pinned revision) is used.
    n_intents intents are a seeded subset of the 77. The out_of_scope class is borrowed
    from CLINC150's OOS utterances (cross-dataset: a style shift may make OOS easier
    to spot than in "clinc150"; documented caveat).
    train and calibration are disjoint seeded draws from Banking77 train; test is drawn
    from Banking77 test.

per_class
    Maximum items per class per split: {"train": 100, "calibration": 10, "test": 15}
    by default. Keys you omit keep their default. The out_of_scope class gets the same
    count as an in-scope class unless you pass "oos_train" / "oos_calibration" /
    "oos_test". Requests above what the source has are capped (CLINC has 100 train
    utterances per intent, so a C1a sweep at N=200 is capped at 100; Banking77 train
    has ~100-180 per intent, minus the calibration draw). Default test size:
    16 classes x 15 = 240 items (>= 200, per the Local Lab gate).

Raw parquet downloads go to lab/data/raw/ (gitignored). The processed task is cached as
small JSONL under lab/data/ (safe to commit), so tests and LAB-B can run offline.
Downloaded files are untrusted data: only parquet files are read (pyarrow), no dataset
loading scripts are executed, and README front-matter is parsed with yaml.safe_load only
when needed (it is not needed: label names come from the parquet schema metadata).
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path
from typing import Iterable

from .types import Item, Split, Task

LAB_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = LAB_DIR / "data"
RAW_DIR = DATA_DIR / "raw"

OOS_LABEL = "out_of_scope"

DEFAULT_PER_CLASS = {"train": 100, "calibration": 10, "test": 15}

# Pinned dataset revisions (LL6-style pinning, applied to data too).
CLINC_REPO = "clinc/clinc_oos"
CLINC_REV = "155b9c710419136e17307b80d0a13e68cd46b4ec"
CLINC_FILES = {
    "train": "plus/train-00000-of-00001.parquet",
    "validation": "plus/validation-00000-of-00001.parquet",
    "test": "plus/test-00000-of-00001.parquet",
}
B77_REPO = "legacy-datasets/banking77"
B77_REV = "f54121560de48f2852f90be299010d1d6dc612ec"
B77_FILES = {
    "train": "data/train-00000-of-00001.parquet",
    "test": "data/test-00000-of-00001.parquet",
}

INSTRUCTIONS = (
    "A customer sent this message to a bank's support assistant. Which option best "
    "describes what the customer wants? Pick exactly one option. Pick out_of_scope if "
    "the message is not about any of the listed banking requests."
)

OOS_DESCRIPTION = "None of the listed requests: anything else, including non-banking chit-chat or tasks"

# ---------------------------------------------------------------------------
# Human-written label descriptions (Jev 'criteria' text)
# ---------------------------------------------------------------------------
CLINC_BANKING = [
    "transfer", "transactions", "balance", "freeze_account", "pay_bill", "bill_balance",
    "bill_due", "interest_rate", "routing", "min_payment", "order_checks", "pin_change",
    "report_fraud", "account_blocked", "spending_history",
]
CLINC_CREDIT_CARDS = [
    "credit_score", "report_lost_card", "credit_limit", "rewards_balance", "new_card",
    "application_status", "card_declined", "international_fees", "apr", "redeem_rewards",
    "credit_limit_change", "damaged_card", "replacement_card_duration", "expiration_date",
    "improve_credit_score",
]
CLINC_DESCRIPTIONS = {
    # banking domain
    "transfer": "Move money between accounts or send money to someone",
    "transactions": "See recent transactions or a specific charge on the account",
    "balance": "Ask how much money is in an account",
    "freeze_account": "Freeze or lock an account",
    "pay_bill": "Pay a bill",
    "bill_balance": "Ask how much is owed on a bill",
    "bill_due": "Ask when a bill is due",
    "interest_rate": "Ask what interest rate an account earns or charges",
    "routing": "Ask for the bank's routing number",
    "min_payment": "Ask for the minimum payment due",
    "order_checks": "Order new paper checks / a checkbook",
    "pin_change": "Change or reset a PIN",
    "report_fraud": "Report fraud or a transaction the customer did not make",
    "account_blocked": "Account is blocked or locked and the customer cannot use it",
    "spending_history": "Ask how much was spent on something over a period",
    # credit_cards domain
    "credit_score": "Ask what their credit score is",
    "report_lost_card": "Report a lost or stolen card",
    "credit_limit": "Ask what the credit limit is",
    "rewards_balance": "Ask how many reward points they have",
    "new_card": "Apply for a new credit card",
    "application_status": "Ask about the status of a card application",
    "card_declined": "Ask why a card was declined",
    "international_fees": "Ask about fees for using a card abroad",
    "apr": "Ask what the APR on a card is",
    "redeem_rewards": "Ask how to redeem or use reward points",
    "credit_limit_change": "Ask to raise or change the credit limit",
    "damaged_card": "Card is damaged or broken",
    "replacement_card_duration": "Ask how long a replacement card takes to arrive",
    "expiration_date": "Ask when a card expires",
    "improve_credit_score": "Ask how to improve a credit score",
}

B77_DESCRIPTIONS = {
    "activate_my_card": "Activate a newly received card",
    "age_limit": "Ask the minimum age to open an account",
    "apple_pay_or_google_pay": "Use or set up Apple Pay or Google Pay",
    "atm_support": "Ask where ATMs are or which ATMs accept the card",
    "automatic_top_up": "Set up or ask about automatic top-ups",
    "balance_not_updated_after_bank_transfer": "Balance did not update after a bank transfer in",
    "balance_not_updated_after_cheque_or_cash_deposit": "Balance did not update after a cheque or cash deposit",
    "beneficiary_not_allowed": "Cannot add or pay a beneficiary/payee",
    "cancel_transfer": "Cancel a transfer that was already sent",
    "card_about_to_expire": "Card is about to expire; ask about renewal",
    "card_acceptance": "Ask where the card is accepted",
    "card_arrival": "Ordered card has not arrived yet",
    "card_delivery_estimate": "Ask how long card delivery takes",
    "card_linking": "Link an existing card to the app/account",
    "card_not_working": "Card is not working",
    "card_payment_fee_charged": "Unexpected fee charged on a card payment",
    "card_payment_not_recognised": "Card payment the customer does not recognise",
    "card_payment_wrong_exchange_rate": "Wrong exchange rate applied to a card payment",
    "card_swallowed": "ATM kept/swallowed the card",
    "cash_withdrawal_charge": "Charged a fee for a cash withdrawal",
    "cash_withdrawal_not_recognised": "Cash withdrawal the customer does not recognise",
    "change_pin": "Change the card PIN",
    "compromised_card": "Card details may be compromised or used by someone else",
    "contactless_not_working": "Contactless payment does not work",
    "country_support": "Ask which countries are supported",
    "declined_card_payment": "Card payment was declined",
    "declined_cash_withdrawal": "Cash withdrawal was declined",
    "declined_transfer": "Transfer was declined",
    "direct_debit_payment_not_recognised": "Direct debit the customer does not recognise",
    "disposable_card_limits": "Ask about limits on disposable virtual cards",
    "edit_personal_details": "Change name, address or other personal details",
    "exchange_charge": "Ask about fees for currency exchange",
    "exchange_rate": "Ask what exchange rate is used",
    "exchange_via_app": "Exchange currency in the app",
    "extra_charge_on_statement": "Unexplained extra charge on the statement",
    "failed_transfer": "Transfer failed",
    "fiat_currency_support": "Ask which fiat currencies are supported",
    "get_disposable_virtual_card": "Get a disposable virtual card",
    "get_physical_card": "Get a physical card",
    "getting_spare_card": "Get an additional/spare card",
    "getting_virtual_card": "Get a virtual card",
    "lost_or_stolen_card": "Card was lost or stolen",
    "lost_or_stolen_phone": "Phone with the app was lost or stolen",
    "order_physical_card": "Order a physical card",
    "passcode_forgotten": "Forgot the app passcode",
    "pending_card_payment": "Card payment is still pending",
    "pending_cash_withdrawal": "Cash withdrawal is still pending",
    "pending_top_up": "Top-up is still pending",
    "pending_transfer": "Transfer is still pending",
    "pin_blocked": "PIN is blocked after wrong attempts",
    "receiving_money": "Ask how to receive money",
    "refund_not_showing_up": "Expected refund has not appeared",
    "request_refund": "Ask for a refund",
    "reverted_card_payment": "Card payment was reverted",
    "supported_cards_and_currencies": "Ask which cards and currencies are supported",
    "terminate_account": "Close or delete the account",
    "top_up_by_bank_transfer_charge": "Fee for topping up by bank transfer",
    "top_up_by_card_charge": "Fee for topping up by card",
    "top_up_by_cash_or_cheque": "Top up with cash or a cheque",
    "top_up_failed": "Top-up failed",
    "top_up_limits": "Ask about top-up limits",
    "top_up_reverted": "Top-up was reverted",
    "topping_up_by_card": "Top up using a card",
    "transaction_charged_twice": "Charged twice for the same transaction",
    "transfer_fee_charged": "Charged a fee for a transfer",
    "transfer_into_account": "Transfer money into the account",
    "transfer_not_received_by_recipient": "Recipient has not received a transfer",
    "transfer_timing": "Ask how long a transfer takes",
    "unable_to_verify_identity": "Identity verification is not working",
    "verify_my_identity": "How to verify identity",
    "verify_source_of_funds": "Verify the source of funds",
    "verify_top_up": "Verify a top-up",
    "virtual_card_not_working": "Virtual card is not working",
    "visa_or_mastercard": "Ask whether the card is Visa or Mastercard",
    "why_verify_identity": "Ask why identity verification is needed",
    "wrong_amount_of_cash_received": "ATM gave the wrong amount of cash",
    "wrong_exchange_rate_for_cash_withdrawal": "Wrong exchange rate on a cash withdrawal",
}


def _norm_label(name: str) -> str:
    """Normalise source label names into stable snake_case option ids."""
    return re.sub(r"[^a-z0-9_]+", "", name.strip().lower().replace(" ", "_"))


def _humanize(label: str) -> str:
    return label.replace("_", " ").capitalize()


# ---------------------------------------------------------------------------
# Raw access
# ---------------------------------------------------------------------------
def _fetch(repo: str, rev: str, filename: str, subdir: str) -> Path:
    local = RAW_DIR / subdir / filename
    if local.exists():
        return local
    from huggingface_hub import hf_hub_download  # network only when cache is cold

    p = hf_hub_download(repo, filename, repo_type="dataset", revision=rev, local_dir=str(RAW_DIR / subdir))
    return Path(p)


def _read_parquet(path: Path, label_col: str) -> tuple[list[tuple[int, str, str]], list[str]]:
    """Return ([(row_index, text, label_name)], label_names) from a parquet file."""
    import pyarrow.parquet as pq

    table = pq.read_table(str(path))
    meta = json.loads(table.schema.metadata[b"huggingface"])
    names = meta["info"]["features"][label_col]["names"]
    texts = table.column("text").to_pylist()
    labels = table.column(label_col).to_pylist()
    rows = [(i, str(t), names[int(l)]) for i, (t, l) in enumerate(zip(texts, labels))]
    return rows, names


def _group(rows: Iterable[tuple[int, str, str]]) -> dict[str, list[tuple[int, str]]]:
    g: dict[str, list[tuple[int, str]]] = {}
    for idx, text, lab in rows:
        g.setdefault(lab, []).append((idx, text))
    return g


def _sample(pool: list[tuple[int, str]], n: int, rng: random.Random) -> list[tuple[int, str]]:
    pool = sorted(pool)  # deterministic base order before seeded shuffle
    rng.shuffle(pool)
    return pool[: min(n, len(pool))]


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------
def _resolve_per_class(per_class: dict[str, int] | None) -> dict[str, int]:
    pc = dict(DEFAULT_PER_CLASS)
    if per_class:
        unknown = set(per_class) - {"train", "calibration", "test", "oos_train", "oos_calibration", "oos_test"}
        if unknown:
            raise ValueError(f"unknown per_class keys: {sorted(unknown)}")
        pc.update({k: int(v) for k, v in per_class.items()})
    for s in ("train", "calibration", "test"):
        pc.setdefault(f"oos_{s}", pc[s])
    return pc


def _clinc_pick_intents(n_intents: int, seed: int, all_names: list[str]) -> list[str]:
    rng = random.Random(seed)
    if n_intents <= len(CLINC_BANKING):
        if n_intents == len(CLINC_BANKING):
            return list(CLINC_BANKING)
        return sorted(rng.sample(CLINC_BANKING, n_intents))
    picked = list(CLINC_BANKING)
    extra = n_intents - len(picked)
    if extra <= len(CLINC_CREDIT_CARDS):
        return picked + sorted(rng.sample(CLINC_CREDIT_CARDS, extra))
    picked += CLINC_CREDIT_CARDS
    rest = sorted(n for n in all_names if n not in picked and n != "oos")
    extra = n_intents - len(picked)
    if extra > len(rest):
        raise ValueError(f"clinc150 has only 150 intents; asked for {n_intents}")
    return picked + sorted(rng.sample(rest, extra))


def _build_clinc(n_intents: int, seed: int, pc: dict[str, int]) -> Task:
    src = {k: _read_parquet(_fetch(CLINC_REPO, CLINC_REV, f, "clinc_oos"), "intent") for k, f in CLINC_FILES.items()}
    names = src["train"][1]
    intents = _clinc_pick_intents(n_intents, seed, names)
    split_map: dict[Split, str] = {"train": "train", "calibration": "validation", "test": "test"}
    items: list[Item] = []
    name = f"clinc150-{'banking15' if intents == CLINC_BANKING else f'n{n_intents}'}+oos"
    for split, src_split in split_map.items():
        groups = _group(src[src_split][0])
        for lab in intents + ["oos"]:
            rng = random.Random(f"{seed}:{split}:{lab}")
            n = pc[f"oos_{split}"] if lab == "oos" else pc[split]
            out_lab = OOS_LABEL if lab == "oos" else lab
            for idx, text in _sample(groups.get(lab, []), n, rng):
                items.append(Item(id=f"clinc:{src_split}:{idx}", text=text, label=out_lab, split=split))
    labels = tuple(intents) + (OOS_LABEL,)
    desc = {l: CLINC_DESCRIPTIONS.get(l, _humanize(l)) for l in intents}
    desc[OOS_LABEL] = OOS_DESCRIPTION
    return Task(
        name=name,
        instructions=INSTRUCTIONS,
        labels=labels,
        label_descriptions=desc,
        items=tuple(items),
        source=f"CLINC150 ({CLINC_REPO}, config 'plus', CC-BY-3.0) @ {CLINC_REV}; https://huggingface.co/datasets/{CLINC_REPO}",
        seed=seed,
    )


def _build_banking77(n_intents: int, seed: int, pc: dict[str, int]) -> Task:
    tr_rows, names = _read_parquet(_fetch(B77_REPO, B77_REV, B77_FILES["train"], "banking77"), "label")
    te_rows, _ = _read_parquet(_fetch(B77_REPO, B77_REV, B77_FILES["test"], "banking77"), "label")
    clinc = {k: _read_parquet(_fetch(CLINC_REPO, CLINC_REV, f, "clinc_oos"), "intent")[0] for k, f in CLINC_FILES.items()}
    if not 1 <= n_intents <= len(names):
        raise ValueError(f"banking77 has {len(names)} intents; asked for {n_intents}")
    rng = random.Random(seed)
    chosen_raw = sorted(rng.sample(sorted(names), n_intents)) if n_intents < len(names) else sorted(names)
    tr_g, te_g = _group(tr_rows), _group(te_rows)
    items: list[Item] = []
    for raw in chosen_raw:
        lab = _norm_label(raw)
        r = random.Random(f"{seed}:trainpool:{lab}")
        pool = _sample(tr_g.get(raw, []), 10**9, r)  # full seeded shuffle
        cal = pool[: pc["calibration"]]
        tr = pool[pc["calibration"] : pc["calibration"] + pc["train"]]
        te = _sample(te_g.get(raw, []), pc["test"], random.Random(f"{seed}:test:{lab}"))
        for split, chunk, src_split in (("calibration", cal, "train"), ("train", tr, "train"), ("test", te, "test")):
            for idx, text in chunk:
                items.append(Item(id=f"b77:{src_split}:{idx}", text=text, label=lab, split=split))
    oos_src: dict[Split, str] = {"train": "train", "calibration": "validation", "test": "test"}
    for split, src_split in oos_src.items():
        pool = _group(clinc[src_split]).get("oos", [])
        for idx, text in _sample(pool, pc[f"oos_{split}"], random.Random(f"{seed}:{split}:oos")):
            items.append(Item(id=f"clinc:{src_split}:{idx}", text=text, label=OOS_LABEL, split=split))
    labels = tuple(_norm_label(r) for r in chosen_raw) + (OOS_LABEL,)
    desc = {l: B77_DESCRIPTIONS.get(l, _humanize(l)) for l in labels if l != OOS_LABEL}
    desc[OOS_LABEL] = OOS_DESCRIPTION
    return Task(
        name=f"banking77-n{n_intents}+clincoos",
        instructions=INSTRUCTIONS,
        labels=labels,
        label_descriptions=desc,
        items=tuple(items),
        source=(
            f"Banking77 (PolyAI, CC-BY-4.0) via parquet mirror {B77_REPO} @ {B77_REV}; "
            f"out_of_scope from CLINC150 ({CLINC_REPO}, CC-BY-3.0) @ {CLINC_REV}"
        ),
        seed=seed,
    )


# ---------------------------------------------------------------------------
# Cache + public API
# ---------------------------------------------------------------------------
def _cache_path(name: str, n_intents: int, seed: int, pc: dict[str, int]) -> Path:
    key = json.dumps(pc, sort_keys=True)
    h = hashlib.sha1(key.encode()).hexdigest()[:8]
    return DATA_DIR / f"{name}-n{n_intents}-s{seed}-{h}.jsonl"


def _write_cache(path: Path, task: Task, pc: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = {
        "_header": True,
        "name": task.name,
        "instructions": task.instructions,
        "labels": list(task.labels),
        "label_descriptions": task.label_descriptions,
        "source": task.source,
        "seed": task.seed,
        "per_class": pc,
    }
    with path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(header, ensure_ascii=False) + "\n")
        for it in task.items:
            f.write(json.dumps({"id": it.id, "text": it.text, "label": it.label, "split": it.split}, ensure_ascii=False) + "\n")


def _read_cache(path: Path) -> Task:
    with path.open(encoding="utf-8") as f:
        header = json.loads(f.readline())
        items = tuple(Item(**json.loads(line)) for line in f if line.strip())
    return Task(
        name=header["name"],
        instructions=header["instructions"],
        labels=tuple(header["labels"]),
        label_descriptions=dict(header["label_descriptions"]),
        items=items,
        source=header["source"],
        seed=int(header["seed"]),
    )


TASKS = ("clinc150", "banking77")


def load_task(name: str = "clinc150", n_intents: int = 15, seed: int = 7, per_class: dict[str, int] | None = None) -> Task:
    """Load (from the JSONL cache, else build from pinned parquet) a seeded Choice task.

    name: "clinc150" (default; CLINC banking domain + CLINC OOS) or "banking77".
    Returns a Task whose labels end with "out_of_scope".
    """
    key = name.lower().replace("_", "").replace("-", "")
    if key in ("clinc150", "clinc", "clincoos"):
        key = "clinc150"
    elif key in ("banking77", "banking"):
        key = "banking77"
    else:
        raise ValueError(f"unknown task {name!r}; choose from {TASKS}")
    pc = _resolve_per_class(per_class)
    path = _cache_path(key, n_intents, seed, pc)
    if path.exists():
        return _read_cache(path)
    task = _build_clinc(n_intents, seed, pc) if key == "clinc150" else _build_banking77(n_intents, seed, pc)
    _check(task)
    _write_cache(path, task, pc)
    return task


def _check(task: Task) -> None:
    ids = [it.id for it in task.items]
    if len(ids) != len(set(ids)):
        raise AssertionError("duplicate item ids across splits (leakage)")
    bad = {it.label for it in task.items} - set(task.labels)
    if bad:
        raise AssertionError(f"items with labels outside task.labels: {bad}")
    if set(task.label_descriptions) != set(task.labels):
        raise AssertionError("label_descriptions must cover exactly task.labels")


def task_summary(task: Task) -> dict:
    """Counts per split and per label (for logs)."""
    out: dict = {"name": task.name, "n_labels": len(task.labels), "splits": {}}
    for s in ("train", "calibration", "test"):
        its = task.split(s)  # type: ignore[arg-type]
        per = {}
        for it in its:
            per[it.label] = per.get(it.label, 0) + 1
        out["splits"][s] = {"n": len(its), "min_per_class": min(per.values()) if per else 0, "max_per_class": max(per.values()) if per else 0}
    return out
