"""Tests for bioRxiv/medRxiv /pubs endpoint (T-0930)."""

import json
from pathlib import Path
import unittest

from evidence.http import Client
from evidence.providers import preprints
from evidence.record import Evidence, Status

FX = Path(__file__).parent / "fixtures"


class TestPreprintsPubs(unittest.TestCase):
    def setUp(self):
        self.raw_data = json.loads((FX / "preprints_pubs.json").read_text(encoding="utf-8"))

    def test_parse_pubs_published_record(self):
        recs = preprints.parse_pubs(self.raw_data, "biorxiv", "q", "https://api.biorxiv.org/pubs/biorxiv/10.1101/2020.01.01.123456")
        self.assertEqual(len(recs), 2)
        pub_rec = recs[0]
        self.assertEqual(pub_rec.status, Status.FOUND)
        self.assertEqual(pub_rec.fields["preprint_doi"], "10.1101/2020.01.01.123456")
        self.assertEqual(pub_rec.fields["published_doi"], "10.1038/s41586-020-1234-5")
        self.assertEqual(pub_rec.fields["published_journal"], "Nature")
        self.assertTrue(pub_rec.fields["is_published"])
        self.assertEqual(pub_rec.fields["status_label"], "PUBLISHED")
        self.assertIn("Published as 10.1038/s41586-020-1234-5 in Nature", pub_rec.excerpt)
        self.assertIn("peer-reviewed journal citation should be preferred", pub_rec.limitations)

    def test_parse_pubs_unpublished_preprint(self):
        recs = preprints.parse_pubs(self.raw_data, "medrxiv", "q", "https://api.biorxiv.org/pubs/medrxiv/10.1101/2025.02.14.25322057")
        unpub_rec = recs[1]
        self.assertEqual(unpub_rec.status, Status.FOUND)
        self.assertEqual(unpub_rec.fields["preprint_doi"], "10.1101/2025.02.14.25322057")
        self.assertIsNone(unpub_rec.fields["published_doi"])
        self.assertIsNone(unpub_rec.fields["published_journal"])
        self.assertFalse(unpub_rec.fields["is_published"])
        self.assertEqual(unpub_rec.fields["status_label"], "UNPUBLISHED_PREPRINT")
        self.assertIn("Unpublished preprint", unpub_rec.excerpt)

    def test_parse_pubs_empty_collection(self):
        empty_data = {"messages": [{"status": "ok"}], "collection": []}
        recs = preprints.parse_pubs(empty_data, "biorxiv", "q", "url")
        self.assertEqual(recs, [])

    def test_lookup_published_with_mock_client(self):
        class MockClient:
            def get(self, source, path, params=None):
                from evidence.http import Fetch
                if "10.1101/2020.01.01.123456" in path:
                    return Fetch(Status.FOUND, 200, f"https://api.biorxiv.org/{path}", {
                        "collection": [{
                            "biorxiv_doi": "10.1101/2020.01.01.123456",
                            "published_doi": "10.1038/s41586-020-1234-5",
                            "published_journal": "Nature",
                            "published_date": "2020-05-15",
                        }]
                    })
                return Fetch(Status.FOUND, 200, f"https://api.biorxiv.org/{path}", {"collection": []})

        client = MockClient()
        res = preprints.lookup_published(client, "10.1101/2020.01.01.123456")
        self.assertEqual(len(res), 1)
        self.assertTrue(res[0].fields["is_published"])
        self.assertEqual(res[0].fields["published_doi"], "10.1038/s41586-020-1234-5")

        # Test unpublished preprint lookup fallback
        res_unpub = preprints.lookup_published(client, "10.1101/unknown.999999")
        self.assertEqual(len(res_unpub), 1)
        self.assertFalse(res_unpub[0].fields["is_published"])
        self.assertEqual(res_unpub[0].fields["status_label"], "UNPUBLISHED_PREPRINT")


if __name__ == "__main__":
    unittest.main()
