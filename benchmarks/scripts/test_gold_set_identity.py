#!/usr/bin/env python3
"""The gold-set identity rules: a recorded ranking run must name the corpus its label measures.

A ``gold_set`` label is a promise about which gold corpus the run measured, so the
provenance block has to name that corpus, state its hash, and stay internally
consistent about it. Those rules are one subject, and they are tested here rather than
mixed in with the per-run and percentile rules.

The harness is shared with `test_check_reproducibility`: one `CheckerCase`, one loaded
copy of the checker, and the same run fixtures.
"""

from __future__ import annotations

import unittest

from test_check_reproducibility import (
    OTHER_HASH,
    CheckerCase,
    _ranking,
    _ranking_run,
    _recorded,
    check,
    provenance,
)


def _gold_identity(gold_set: str) -> tuple[str, str, str]:
    """``(file, hash, manifest)`` of the gold corpus a ``gold_set`` label names."""
    corpus = check.GOLD_SETS[gold_set]
    corpus_hash, manifest = provenance.corpus_identity(corpus.kind)
    return corpus.name, corpus_hash, manifest


def _gold_recorded(gold_set: str = "v1", **overrides: object) -> dict[str, object]:
    """A recorded block for a run on ``gold_set``, carrying that corpus's real identity."""
    name, corpus_hash, manifest = _gold_identity(gold_set)
    block = _recorded(
        corpus_hash=corpus_hash,
        corpus_manifest=manifest,
        gold_set_hash=corpus_hash,
        gold_set_name=name,
    )
    block.update(overrides)
    return block


class TestGoldSetIdentity(CheckerCase):
    """A recorded ranking run must name the gold set its ``gold_set`` label measures."""

    def _problems(self, gold_set: str, block: dict[str, object]) -> list[str]:
        run = _ranking_run(gold_set=gold_set, provenance=block)
        return self.content_problems(
            _ranking(run), "ranking-quality-benchmark-data.json"
        )

    def test_a_v1_run_on_the_v1_corpus_passes(self) -> None:
        self.assert_clean(
            _ranking(_ranking_run(provenance=_gold_recorded())),
            "ranking-quality-benchmark-data.json",
        )

    def test_a_v2_run_on_the_v2_corpus_passes(self) -> None:
        record = _gold_recorded("ranking_quality_v2")

        self.assert_clean(
            _ranking(_ranking_run(gold_set="ranking_quality_v2", provenance=record)),
            "ranking-quality-benchmark-data.json",
        )

    def test_a_v1_label_with_the_v2_corpus_fails(self) -> None:
        # The v1 producer measures gold_set_v1.json; a v2 hash under a v1 label describes a
        # corpus that was not measured.
        _name, corpus_hash, manifest = _gold_identity("ranking_quality_v2")
        record = _gold_recorded(
            corpus_hash=corpus_hash,
            corpus_manifest=manifest,
            gold_set_hash=corpus_hash,
            gold_set_name="gold_set_v2.json",
        )
        problems = self._problems("v1", record)

        self.assertTrue(
            any("gold_set_name" in problem for problem in problems), problems
        )
        self.assertTrue(
            any("gold_set_hash" in problem for problem in problems), problems
        )

    def test_a_contradictory_gold_set_hash_is_named_with_the_file_it_implies(
        self,
    ) -> None:
        problems = self._problems("v1", _gold_recorded(gold_set_hash=OTHER_HASH))

        self.assertTrue(
            any(
                "provenance.gold_set_hash: '000" in problem
                and "implies for gold_set_v1.json" in problem
                for problem in problems
            ),
            problems,
        )

    def test_a_recorded_run_without_the_gold_set_name_fails(self) -> None:
        record = _gold_recorded()
        del record["gold_set_name"]
        problems = self._problems("v1", record)

        self.assertTrue(
            any("provenance.gold_set_name" in problem for problem in problems), problems
        )

    def test_an_older_gold_set_recorded_as_stale_passes(self) -> None:
        # A run measured on a previous generation of the v1 gold set keeps the hash it measured and
        # says "stale" about it. The bytes in this checkout are not its business, so retaining it
        # cannot turn the check red; the record is still internally consistent.
        older = "1" * 64
        record = _gold_recorded(
            corpus_hash=older,
            corpus_manifest=f"gold_set_v1.json={older}",
            gold_set_hash=older,
            corpus_status="stale",
        )

        self.assert_clean(
            _ranking(_ranking_run(provenance=record)),
            "ranking-quality-benchmark-data.json",
        )

    def test_a_stale_run_that_states_two_corpus_hashes_fails(self) -> None:
        # Skipping the checkout comparison is not skipping consistency: the gold set is the corpus
        # on this benchmark, so gold_set_hash and corpus_hash cannot name different bytes.
        record = _gold_recorded(
            corpus_hash="1" * 64, gold_set_hash="2" * 64, corpus_status="stale"
        )
        problems = self._problems("v1", record)

        self.assertTrue(
            any(
                "provenance.gold_set_hash: '222" in problem
                and "!= corpus_hash" in problem
                for problem in problems
            ),
            problems,
        )

    def test_a_stale_run_that_names_the_other_generation_fails(self) -> None:
        # The label-to-file map needs no checked-out bytes, so it holds for an older run too.
        record = _gold_recorded(corpus_status="stale", gold_set_name="gold_set_v2.json")
        problems = self._problems("v1", record)

        self.assertTrue(
            any("provenance.gold_set_name" in problem for problem in problems), problems
        )

    def test_an_unrecorded_run_is_not_checked_against_a_gold_set(self) -> None:
        self.assert_clean(
            _ranking(_ranking_run(gold_set="v1")), "ranking-quality-benchmark-data.json"
        )


if __name__ == "__main__":
    unittest.main()
