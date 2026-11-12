"""The v1 ranking producer must not publish a copy under the canonical corpus's hash.

``run_bench`` seeds whatever ``--gold`` names but emits ``provenance_record("gold_v1")``, which
always hashes the canonical ``gold_set_v1.json``. A copy at another path would therefore be
measured while the artifact claimed the canonical file's digest. These tests pin that refusal,
mirroring ``run_modes.require_v2_gold_set`` for the v2 corpus.
"""

from __future__ import annotations

from pathlib import Path

import bench_ranking_quality as bench
import pytest
from provenance import GOLD_V1_SET_PATH


class TestV1GoldSetGuard:
    def test_a_copy_of_the_corpus_is_refused(self, tmp_path: Path) -> None:
        # It has the right name and shape, but its hash would be published as the canonical
        # file's digest, which is exactly the claim provenance exists to make checkable.
        copy = tmp_path / "gold_set_v1.json"
        copy.write_text("{}", encoding="utf-8")

        with pytest.raises(RuntimeError, match="not the canonical"):
            bench.require_v1_gold_set(copy, {"gold_set": "v1"})

    def test_a_corpus_declaring_another_gold_set_is_refused(self) -> None:
        with pytest.raises(RuntimeError, match="declares gold_set 'v2', expected 'v1'"):
            bench.require_v1_gold_set(GOLD_V1_SET_PATH, {"gold_set": "v2"})

    def test_a_v2_gold_set_name_is_refused(self) -> None:
        # The canonical-path check would also catch this, but the filename is the first thing a
        # wrong `--gold` changes, so the message should say so.
        with pytest.raises(RuntimeError, match="not 'gold_set_v1.json'"):
            bench.require_v1_gold_set(
                GOLD_V1_SET_PATH.with_name("gold_set_v2.json"), {"gold_set": "v1"}
            )

    def test_the_canonical_v1_corpus_passes(self) -> None:
        bench.require_v1_gold_set(GOLD_V1_SET_PATH, {"gold_set": "v1"})
