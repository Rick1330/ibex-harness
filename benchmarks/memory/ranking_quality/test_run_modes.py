"""Tests for the live mode driver: the loop, the recording, and its round trip.

No database. The driver's only interesting logic is what it records and what it refuses, so the
page lookup is injected; `run_all` itself is one seeding call and a loop over modes.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_RANK_DIR = Path(__file__).resolve().parent
_MEMORY_DIR = _RANK_DIR.parents[2] / "services" / "memory"
for _path in (_MEMORY_DIR, _RANK_DIR.parent, _RANK_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import rerank_stub
import run_modes
from bench_ranking_modes import load_recorded
from modes import FULL_GRAPH, HYBRID, MODES


def _payload(*queries: dict[str, Any]) -> dict[str, Any]:
    return {"topics": {"alpha": 0, "beta": 1}, "queries": list(queries)}


def _query(**overrides: Any) -> dict[str, Any]:
    base = {
        "query_id": "q1",
        "subset": "dense",
        "query_text": "how long are backups kept",
        "embedding_profile": {"alpha": 1.0},
        "expected_content_keys": ["mem-a", "mem-b"],
    }
    base.update(overrides)
    return base


class _Hit:
    def __init__(self, memory_id: str) -> None:
        self.id = memory_id


class _RecordingRepo:
    """Stands in for the repository: returns a fixed page and remembers the query it was given."""

    def __init__(self, hits: list[_Hit]) -> None:
        self.hits = hits
        self.queries: list[Any] = []

    async def find_similar(self, query: Any) -> list[_Hit]:
        self.queries.append(query)
        return self.hits


class TestQuerySpecs:
    def test_every_query_gets_a_unit_vector_over_the_declared_topics(self) -> None:
        specs = run_modes.query_specs(_payload(_query()))

        assert len(specs) == 1
        assert len(specs[0].vector) == 1024
        assert specs[0].expected_ids == ("mem-a", "mem-b")

    def test_expected_id_order_is_preserved(self) -> None:
        # The order is the labeler's ranking of the relevant ids; sorting it here would quietly
        # rewrite the judgment before it is recorded.
        specs = run_modes.query_specs(_payload(_query(expected_content_keys=["mem-z", "mem-a"])))

        assert specs[0].expected_ids == ("mem-z", "mem-a")

    def test_a_v1_query_is_named_when_it_has_no_profile(self) -> None:
        query = _query()
        del query["embedding_profile"]
        payload = _payload(query)

        with pytest.raises(run_modes.RunModeError, match=r"'q1' has no embedding_profile"):
            run_modes.query_specs(payload)

    def test_a_corpus_without_topics_is_rejected(self) -> None:
        # Without the topic map the profile is a dict of names, and a vector cannot be built; a
        # silent fallback would seed one geometry and query another.
        payload = {"queries": [_query()], "topics": {}}

        with pytest.raises(run_modes.RunModeError, match="must declare its topics"):
            run_modes.query_specs(payload)


class TestRunMode:
    def _search(
        self, repo: _RecordingRepo, id_to_key: dict[str, str], *, floor: float = 0.5
    ) -> run_modes.SearchPage:
        return run_modes.page_search(
            repo,  # type: ignore[arg-type]
            _Seed(),  # type: ignore[arg-type]
            id_to_key,
            min_similarity=floor,
        )

    def test_the_page_is_recorded_verbatim(self) -> None:
        spec = run_modes.QuerySpec("q1", "dense", "text", [1.0], ("mem-a",))
        repo = _RecordingRepo([_Hit("mem-a"), _Hit("mem-b")])

        outcomes = asyncio.run(
            run_modes.run_mode(self._search(repo, {"mem-a": "mem-a", "mem-b": "mem-b"}), [spec])
        )

        assert outcomes[0].ranked_ids == ("mem-a", "mem-b")
        assert outcomes[0].expected_ids == ("mem-a",)
        assert outcomes[0].subset == "dense"

    def test_a_short_page_is_not_padded(self) -> None:
        # A mode that returns one id when ten were asked for is a result about that mode; filling
        # the page would hide it behind whatever the fixtures happened to contain.
        spec = run_modes.QuerySpec("q1", "dense", "text", [1.0], ("mem-a",))

        async def search(_spec: run_modes.QuerySpec) -> list[str]:
            return ["mem-a"]

        outcomes = asyncio.run(run_modes.run_mode(search, [spec]))

        assert outcomes[0].ranked_ids == ("mem-a",)

    def test_hits_outside_the_corpus_are_dropped_and_order_is_kept(self) -> None:
        spec = run_modes.QuerySpec("q1", "dense", "text", [1.0], ("mem-a",))
        repo = _RecordingRepo([_Hit("stranger"), _Hit("mem-b"), _Hit("mem-a")])
        search = self._search(repo, {"mem-a": "mem-a", "mem-b": "mem-b"})

        outcomes = asyncio.run(run_modes.run_mode(search, [spec]))

        assert outcomes[0].ranked_ids == ("mem-b", "mem-a")

    def test_the_repository_is_asked_for_one_page_with_the_corpus_floor(self) -> None:
        spec = run_modes.QuerySpec("q1", "dense", "text", [1.0], ("mem-a",))
        repo = _RecordingRepo([])

        asyncio.run(self._search(repo, {}, floor=0.42)(spec))

        asked = repo.queries[0]
        assert asked.query_text == "text"
        assert (asked.limit, asked.min_similarity) == (10, 0.42)


class _Seed:
    org_id = "org-fixed"
    agent_id = "agent-fixed"


_PROVENANCE = {
    "status": "recorded",
    "producer": "benchmarks/memory/provenance.py",
    "corpus_hash": "1" * 64,
    "corpus_hash_algo": "sha256",
    "corpus_manifest": "gold_set_v2.json=" + "1" * 64,
    "corpus_status": "current",
    "dirty": False,
    "gold_set_hash": "1" * 64,
    "gold_set_name": "gold_set_v2.json",
}


class TestProvenance:
    def test_gold_provenance_names_the_corpus_and_its_state(self) -> None:
        # The recording has to carry the three fields a reader needs to identify the gold set
        # without this driver's help, and they come from the one hash implementation.
        record = run_modes.gold_set_provenance()

        assert record["gold_set_name"] == "gold_set_v2.json"
        assert len(record["gold_set_hash"]) == 64
        assert record["corpus_status"] in {"current", "stale"}

    def test_a_recording_without_gold_provenance_is_refused(self) -> None:
        with pytest.raises(run_modes.RunModeError, match="missing gold_set_hash, corpus_status"):
            run_modes.build_recording(
                {"hybrid": []},
                run_modes.RecordingContext(
                    reranker="stub/lexical-overlap@1",
                    gold_set="ranking_quality_v2",
                    recorded_at="2026-11-04T00:00:00+00:00",
                    provenance={"gold_set_name": "gold_set_v2.json"},
                ),
            )

    def test_a_v1_gold_set_name_is_refused(self) -> None:
        # The canonical path check would also catch this, but the name is the first thing a
        # reader sees and the first thing a wrong `--gold-set` changes.
        with pytest.raises(run_modes.RunModeError, match="not 'gold_set_v2.json'"):
            run_modes.require_v2_gold_set(
                run_modes.DEFAULT_GOLD_SET.with_name("gold_set_v1.json"),
                {"gold_set": "ranking_quality_v1"},
            )

    def test_a_copy_of_the_corpus_is_refused(self, tmp_path: Path) -> None:
        # It has the right name and shape, but its hash would be published as the canonical
        # file's digest, which is exactly the claim provenance exists to make checkable.
        copy = tmp_path / "gold_set_v2.json"
        copy.write_text("{}", encoding="utf-8")

        with pytest.raises(run_modes.RunModeError, match="not the canonical"):
            run_modes.require_v2_gold_set(copy, {"gold_set": "ranking_quality_v2"})

    def test_a_corpus_declaring_another_gold_set_is_refused(self) -> None:
        with pytest.raises(run_modes.RunModeError, match="declares gold_set 'ranking_quality_v1'"):
            run_modes.require_v2_gold_set(
                run_modes.DEFAULT_GOLD_SET, {"gold_set": "ranking_quality_v1"}
            )

    def test_the_canonical_v2_corpus_passes(self) -> None:
        run_modes.require_v2_gold_set(
            run_modes.DEFAULT_GOLD_SET, {"gold_set": "ranking_quality_v2"}
        )


class TestRecording:
    def test_the_recording_names_what_produced_it(self) -> None:
        recording = run_modes.build_recording(
            {"hybrid": []},
            run_modes.RecordingContext(
                reranker="stub/lexical-overlap@1",
                gold_set="ranking_quality_v2",
                recorded_at="2026-11-04T00:00:00+00:00",
                provenance=_PROVENANCE,
            ),
        )

        assert recording["reranker"] == "stub/lexical-overlap@1"
        assert recording["gold_set"] == "ranking_quality_v2"
        assert recording["benchmark"] == "ranking_quality"
        assert recording["provenance"] == _PROVENANCE

    def test_the_recording_is_readable_by_the_strict_loader(self, tmp_path: Path) -> None:
        # The driver and the scorer only agree because the recording format is one definition.
        # Round-tripping it here is what stops a driver change from publishing unlabelled rows.
        recording = run_modes.build_recording(
            {
                "hybrid": [
                    run_modes.QueryOutcome(
                        query_id="q1",
                        subset="dense",
                        ranked_ids=("mem-a",),
                        expected_ids=("mem-a",),
                    )
                ]
            },
            run_modes.RecordingContext(
                reranker="stub/lexical-overlap@1",
                gold_set="ranking_quality_v2",
                recorded_at="2026-11-04T00:00:00+00:00",
                provenance=_PROVENANCE,
            ),
        )
        path = tmp_path / "recording.json"
        path.write_text(json.dumps(recording), encoding="utf-8")

        loaded = load_recorded(path)

        assert loaded.reranker == "stub/lexical-overlap@1"
        assert loaded.modes["hybrid"][0].ranked_ids == ("mem-a",)


class TestModeSelection:
    def test_the_requested_order_is_kept(self) -> None:
        selected = run_modes._selected_modes(["full_graph", "hybrid"])

        assert [mode.name for mode in selected] == ["full_graph", "hybrid"]

    def test_an_unknown_mode_is_named(self) -> None:
        with pytest.raises(run_modes.RunModeError, match="unknown modes: dense"):
            run_modes._selected_modes(["hybrid", "dense"])

    def test_every_mode_is_offered_by_default(self) -> None:
        assert len(MODES) == 4
        assert HYBRID.name in [mode.name for mode in MODES]


class TestBaseSettings:
    def test_the_fallback_is_pinned_off_for_every_mode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Only dense_only sets this field, so inheriting it would let a refill add lexical hits
        # to the other three modes and make two runs on different defaults incomparable.
        monkeypatch.setenv("POSTGRES_TEST_DSN", "postgres://u:p@localhost:5433/db")

        settings = run_modes.base_settings()

        assert settings.search_fallback_enabled is False


class TestRerankStub:
    def test_a_document_containing_every_query_term_scores_one(self) -> None:
        assert rerank_stub.overlap_score("backup retention", "backup retention policy") == 1.0

    def test_a_partial_overlap_is_the_share_of_query_terms_found(self) -> None:
        assert rerank_stub.overlap_score(
            "backup retention policy", "backup rotation"
        ) == pytest.approx(1 / 3)

    def test_a_disjoint_document_scores_zero(self) -> None:
        assert rerank_stub.overlap_score("backup retention", "token rotation") == 0.0

    def test_a_query_with_no_usable_terms_scores_zero(self) -> None:
        # Otherwise "a" would match every document that happens to contain the letter.
        assert rerank_stub.overlap_score("a i", "anything at all") == 0.0

    def test_one_character_terms_are_not_query_terms(self) -> None:
        assert rerank_stub.terms("a bb c3 12") == {"bb", "c3", "12"}

    def test_the_client_returns_one_score_per_document_in_order(self) -> None:
        client = rerank_stub.LexicalOverlapReranker()

        scores = asyncio.run(client.rerank("backup retention", ["backup only", "backup retention"]))

        assert scores == [0.5, 1.0]
        assert (client.calls, client.documents_scored) == (1, 2)

    def test_the_label_names_a_stub_rather_than_a_model(self) -> None:
        # Every artifact this touches must say it was not a cross-encoder, so nobody reads the
        # number as a measurement of one.
        assert rerank_stub.LABEL.startswith("stub/")
        assert "lexical-overlap" in rerank_stub.LABEL


class TestRerankGuard:
    def test_a_reranked_mode_that_never_reached_the_reranker_is_refused(self) -> None:
        # The stage skips itself when the fused window is too small, so a run can finish with
        # hybrid_rerank's label and none of its behaviour.
        with pytest.raises(run_modes.RunModeError, match="declares reranking but the reranker"):
            run_modes._require_rerank_ran(FULL_GRAPH, rerank_stub.LexicalOverlapReranker())

    def test_a_mode_without_reranking_is_not_asked_to_have_called_it(self) -> None:
        run_modes._require_rerank_ran(HYBRID, None)

    def test_a_called_reranker_satisfies_the_guard(self) -> None:
        client = rerank_stub.LexicalOverlapReranker()
        asyncio.run(client.rerank("q", ["doc"]))

        run_modes._require_rerank_ran(FULL_GRAPH, client)

    def test_the_non_reranked_modes_get_no_client(self) -> None:
        assert run_modes._rerank_client(HYBRID) is None
        assert run_modes._rerank_client(FULL_GRAPH) is not None

    def test_a_foreign_reranker_label_is_refused_before_anything_is_seeded(
        self,
    ) -> None:
        # run_all must reject this without a database, which also proves the check runs first.
        with pytest.raises(run_modes.RunModeError, match="only runs"):
            asyncio.run(
                run_modes.run_all(
                    gold_path=Path("gold_set_v2.json"),
                    modes=[HYBRID],
                    reranker="bge-reranker-v2-m3",
                )
            )
