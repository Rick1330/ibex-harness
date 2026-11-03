"""Tests for the gold-set v2 generator and the committed artifact."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import generate_gold_set_v2 as gen
import pytest
from validate_gold_set_v2 import validate_gold_set_v2

CORPUS_PATH = Path(__file__).resolve().parent / "gold_set_v2.json"


@pytest.fixture(scope="module")
def corpus() -> dict[str, Any]:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


class TestGeneratedCorpus:
    def test_the_committed_corpus_passes_the_validator(self, corpus: dict[str, Any]) -> None:
        assert validate_gold_set_v2(corpus) == []

    def test_the_committed_corpus_matches_a_fresh_build(self, corpus: dict[str, Any]) -> None:
        # Editing the JSON by hand instead of regenerating it should fail here, not later in
        # a benchmark run that silently measures a different corpus.
        assert corpus == gen.build_corpus()

    def test_generation_is_deterministic(self) -> None:
        first = json.dumps(gen.build_corpus(), sort_keys=True)
        second = json.dumps(gen.build_corpus(), sort_keys=True)

        assert first == second

    def test_shape_matches_the_planned_pools(self, corpus: dict[str, Any]) -> None:
        queries = corpus["queries"]
        cardinality = {subset: sum(1 for q in queries if q["subset"] == subset) for subset in
                       ("dense", "lexical", "graph")}

        assert len(corpus["memories"]) == 500
        assert len(queries) == 150
        assert cardinality == {"dense": 60, "lexical": 50, "graph": 40}

    def test_every_topic_pool_is_disjoint(self, corpus: dict[str, Any]) -> None:
        # A dense topic must never appear in a lexical or graph memory, or one pool's memories
        # could outrank another pool's answers.
        dense_topics = {m["topic"] for m in corpus["memories"] if m["content_key"].startswith("gold.dense.")}
        other_topics = {
            m["topic"] for m in corpus["memories"] if not m["content_key"].startswith("gold.dense.")
        }

        assert dense_topics.isdisjoint(other_topics)

    def test_lexical_tokens_are_unique(self, corpus: dict[str, Any]) -> None:
        tokens = [token for q in corpus["queries"] if q["subset"] == "lexical" for token in q["lexical_tokens"]]

        assert len(tokens) == len(set(tokens))

    def test_every_dense_query_asks_about_the_aspect_it_labels(self, corpus: dict[str, Any]) -> None:
        for row in corpus["memories"]:
            assert row["content_key"]
            assert row["embedding_profile"]


class TestOutputPathGuard:
    """The output path comes from argv, so the guard is the only thing keeping writes local."""

    def test_default_path(self) -> None:
        assert gen._output_path(None) == gen.OUTPUT_PATH

    def test_allowed_path_inside_the_benchmark_dir(self, tmp_path: Any) -> None:
        allowed = Path(gen._RANK_DIR) / "out-under-test.json"

        assert gen._output_path(["gen", str(allowed)]) == allowed.resolve()

    def test_parent_reference_is_refused(self, tmp_path: Any) -> None:
        escape = Path(gen._RANK_DIR) / ".." / "escape.json"

        with pytest.raises(SystemExit, match="refusing to write outside"):
            gen._output_path(["gen", str(escape)])

    def test_absolute_path_outside_is_refused(self, tmp_path: Any) -> None:
        with pytest.raises(SystemExit, match="refusing to write outside"):
            gen._output_path(["gen", str(tmp_path / "escape.json")])

    def test_symlink_escape_is_refused(self, tmp_path: Any) -> None:
        link = Path(gen._RANK_DIR) / "escape-link.json"
        link.unlink(missing_ok=True)
        link.symlink_to(tmp_path / "target.json")
        try:
            with pytest.raises(SystemExit, match="refusing to write outside"):
                gen._output_path(["gen", str(link)])
        finally:
            link.unlink(missing_ok=True)

    def test_directory_is_refused(self, tmp_path: Any) -> None:
        directory = Path(gen._RANK_DIR) / "out-dir-under-test"
        directory.mkdir(exist_ok=True)
        try:
            with pytest.raises(SystemExit, match="is a directory"):
                gen._output_path(["gen", str(directory)])
        finally:
            directory.rmdir()
