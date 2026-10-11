"""Shared fixtures for LAB-B tests (test_b_*.py). Not a conftest, so LAB-A's tests are unaffected."""
from __future__ import annotations

import pytest

from jevlab.stub_server import StubServer
from jevlab.types import Item, Task

LABELS = ("card_arrival", "lost_or_stolen_card", "exchange_rate", "out_of_scope")
DESCS = {
    "card_arrival": "Asks when a newly ordered card will arrive",
    "lost_or_stolen_card": "Reports a lost or stolen card",
    "exchange_rate": "Asks about currency exchange rates",
    "out_of_scope": "None of the listed requests",
}
TEXTS = ["When will my new card get here?", "Someone stole my wallet with my card in it",
         "What rate do you use for euros?", "Tell me a joke", "My card still has not arrived",
         "I lost my card at the station"]


def synthetic_task(n: int = 6, long_rubric: bool = False) -> Task:
    descs = {k: (v + ". ") * 40 if long_rubric else v for k, v in DESCS.items()}
    items = tuple(Item(f"t{i}", TEXTS[i % len(TEXTS)], LABELS[i % 4], "test") for i in range(n))
    items += tuple(Item(f"c{i}", TEXTS[i % len(TEXTS)], LABELS[i % 4], "calibration") for i in range(4))
    return Task(name="synthetic-b", instructions="Which banking intent does this customer message express?",
                labels=LABELS, label_descriptions=descs, items=items, source="synthetic (LAB-B tests)", seed=7)


def stub_fixture():
    @pytest.fixture(scope="module")
    def stub():
        with StubServer() as s:
            yield s

    return stub


def reset(stub: StubServer) -> StubServer:
    stub.reset()
    return stub
