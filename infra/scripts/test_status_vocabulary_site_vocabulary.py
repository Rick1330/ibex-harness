#!/usr/bin/env python3
"""The declared vocabulary in ``ledger.ts``: the ``Status`` union and ``statusMeta``.

These are the labels every surface must name and the label-to-class map they must
agree with, read from the module that declares them.
"""

from __future__ import annotations

import unittest

from status_vocabulary import (
    InputError,
    parse_site_vocabulary,
    parse_status_union,
)
from status_vocabulary_fixtures import SITE_LEDGER


class SiteVocabularyTests(unittest.TestCase):
    def test_the_declared_labels_are_read_from_the_union(self) -> None:
        self.assertEqual(
            parse_status_union(SITE_LEDGER),
            ["IMPLEMENTED", "PROVISIONAL"],
        )

    def test_the_label_to_class_map_is_read_from_status_meta(self) -> None:
        self.assertEqual(
            parse_site_vocabulary(SITE_LEDGER),
            {"IMPLEMENTED": "shipped-local", "PROVISIONAL": "provisional"},
        )

    def test_a_meta_entry_without_a_class_is_an_input_error(self) -> None:
        with self.assertRaises(InputError):
            parse_site_vocabulary(
                "export const statusMeta = {\n  IMPLEMENTED: {\n    label: 'x',\n  },\n}\n"
            )


if __name__ == "__main__":
    unittest.main()
