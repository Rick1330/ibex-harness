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

    def test_a_later_object_does_not_overwrite_the_live_class(self) -> None:
        # The class was read from the span up to the next `LABEL: {` anywhere in the
        # file, so a legacy map below `statusMeta` holding an `IMPLEMENTED` entry
        # replaced the live one: the guard compared `implemented` while the site
        # renders `provisional`. Only `statusMeta`'s own properties are read.
        self.assertEqual(
            parse_site_vocabulary(
                "export const statusMeta: Record<Status, StatusMeta> = {\n"
                "  IMPLEMENTED: {\n"
                "    label: 'Implemented',\n"
                "    ledgerClass: 'provisional',\n"
                "  },\n"
                "}\n"
                "const legacy = {\n"
                "  IMPLEMENTED: {\n"
                "    ledgerClass: 'implemented',\n"
                "  },\n"
                "}\n"
            ),
            {"IMPLEMENTED": "provisional"},
        )

    def test_a_commented_out_class_does_not_win(self) -> None:
        # The class was the first `ledgerClass` in the span, comment or not, so a
        # commented-out value above the live one was compared instead of it. Only a
        # property in code position counts, so both comment forms lose to the real one.
        for comment in ("// ledgerClass: 'implemented',", "/*\n    ledgerClass: 'implemented',\n    */"):
            with self.subTest(comment=comment):
                self.assertEqual(
                    parse_site_vocabulary(
                        "export const statusMeta = {\n"
                        "  IMPLEMENTED: {\n"
                        f"    {comment}\n"
                        "    ledgerClass: 'provisional',\n"
                        "  },\n"
                        "}\n"
                    ),
                    {"IMPLEMENTED": "provisional"},
                )

    def test_a_label_stated_twice_is_an_input_error_naming_both_lines(self) -> None:
        # Two entries for one label cannot be attributed to the live map: keeping the
        # last would compare a class a reader may never see, so the file fails instead.
        with self.assertRaises(InputError) as caught:
            parse_site_vocabulary(
                "export const statusMeta = {\n"
                "  IMPLEMENTED: {\n"
                "    ledgerClass: 'shipped-local',\n"
                "  },\n"
                "  IMPLEMENTED: {\n"
                "    ledgerClass: 'provisional',\n"
                "  },\n"
                "}\n"
            )
        message = str(caught.exception)
        self.assertIn("IMPLEMENTED", message)
        self.assertIn("lines 2 and 5", message)

    def test_a_property_stating_two_classes_is_an_input_error(self) -> None:
        with self.assertRaises(InputError) as caught:
            parse_site_vocabulary(
                "export const statusMeta = {\n"
                "  IMPLEMENTED: {\n"
                "    ledgerClass: 'shipped-local',\n"
                "  },\n"
                "  PROVISIONAL: {\n"
                "    ledgerClass: 'provisional',\n"
                "    ledgerClass: 'shipped-local',\n"
                "  },\n"
                "}\n"
            )
        self.assertIn("PROVISIONAL", str(caught.exception))
        self.assertIn("2 ledgerClass", str(caught.exception))

    def test_a_map_declared_elsewhere_cannot_be_read(self) -> None:
        # `statusMeta = buildMeta()` is a map this file does not contain, and a
        # commented-out declaration is not the live one: each fails rather than
        # reporting a vocabulary read from text that is not the module's map.
        for source in (
            "export const statusMeta = buildMeta()\n",
            "/*\nexport const statusMeta = {\n  IMPLEMENTED: {\n    ledgerClass: 'x',\n  },\n}\n*/\n",
            "function build() {\n  const statusMeta = {\n    IMPLEMENTED: {\n      ledgerClass: 'x',\n    },\n  }\n}\n",
        ):
            with self.subTest(source=source.splitlines()[0]):
                with self.assertRaises(InputError) as caught:
                    parse_site_vocabulary(source)
                self.assertIn("no `statusMeta` object declaration", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
