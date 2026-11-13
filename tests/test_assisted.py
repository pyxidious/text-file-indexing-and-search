"""Protocollo assistito su fixture sintetiche: nessuna conferma sul corpus reale."""
from pathlib import Path
import unittest

from irhome.assisted import record_batch, import_review
from irhome.assisted_freeze import STATUS as ASSISTED_STATUS
from irhome.dataset import csv_rows, write_csv
from irhome.io import sha256, write_json, read_json
from irhome.semantic import prepare, freeze, load_frozen
import test_semantic as synthetic


class AssistedTests(unittest.TestCase):
    setUp = synthetic.SemanticTests.setUp
    rows = synthetic.SemanticTests.rows
    save = synthetic.SemanticTests.save
    complete = synthetic.SemanticTests.complete
    freeze = synthetic.SemanticTests.freeze

    def setup_protocol(self):
        self.complete()
        rows = self.rows()
        self.proposals = self.out / "codex_proposals"
        labels, provenance = [], []
        for r in rows:
            for i in range(1, 11):
                q = f"Q{i:02d}"
                labels.append(dict(doc_id=r["doc_id"], query_id=q, proposed_label=r[q],
                                   confidence="alta", reason="Synthetic fixture known a priori"))
                provenance.append(dict(doc_id=r["doc_id"], query_id=q, proposed_label=r[q],
                                       effective_label=r[q], human_confirmed="0", reviewer="",
                                       confirmation_date="", source="synthetic Codex fixture"))
        write_csv(self.proposals / "complete_labels.csv", labels, list(labels[0]))
        write_csv(self.out / "provenance.csv", provenance, list(provenance[0]))
        _, _, _, identity = prepare(**self.params)
        write_json(self.proposals / "classification_manifest.json",
                   dict(identity=identity, proposals_sha256=sha256(self.proposals / "complete_labels.csv")))
        self.review = [dict(**labels[0], human_label="0", corrected_label="", human_reason="Synthetic fixture only",
                            reviewed_by="fixture", reviewed_at="2026-11-13"),
                       dict(**labels[10], human_label="", corrected_label="", human_reason="",
                            reviewed_by="", reviewed_at="")]
        self.write_review()
        write_json(self.proposals / "review_manifest.json",
                   dict(required_pairs=[dict(doc_id=r["doc_id"], query_id=r["query_id"]) for r in self.review]))
        write_json(self.proposals / "supervision.json", dict(note="Synthetic fixture only"))
        write_csv(self.proposals / "human_corrections.csv", [], ["doc_id", "query_id", "corrected_label"])
        write_csv(self.proposals / "calibration_review.csv", [self.review[0]], list(self.review[0]))

    def write_review(self):
        write_csv(self.proposals / "final_review.csv", self.review, list(self.review[0]))

    def finish_review(self):
        self.review[1].update(human_label="1", human_reason="Synthetic fixture only",
                              reviewed_by="fixture", reviewed_at="2026-11-13")
        self.write_review()

    def test_pending_review_blocks_freeze_before_any_final_file(self):
        self.setup_protocol()
        with self.assertRaisesRegex(ValueError, "Revisione mirata incompleta"):
            self.freeze()
        self.assertFalse((self.out / "frozen.json").exists())
        self.assertFalse((self.out / "final_positives.csv").exists())

    def test_partial_status_and_provenance_immutability(self):
        self.setup_protocol()
        self.finish_review()
        report = self.freeze()
        self.assertEqual(report["status"], ASSISTED_STATUS)
        self.assertFalse(report["supervision"]["full_manual_validation"])
        self.assertEqual(report["supervision"]["human_confirmed_pairs"], 2)
        self.assertEqual(report["supervision"]["unconfirmed_pairs"], 118)
        self.assertEqual(len(load_frozen(**self.params)["Q01"]), 11)
        for path in [self.out / "provenance.csv", self.proposals / "supervision.json",
                     self.proposals / "calibration_review.csv"]:
            original = path.read_bytes()
            path.write_bytes(original + b"\n")
            try:
                with self.assertRaisesRegex(ValueError, "Provenienza modificata"):
                    load_frozen(**self.params)
            finally:
                path.write_bytes(original)

    def test_missing_provenance_cannot_fall_back_to_human_status(self):
        self.setup_protocol()
        self.finish_review()
        (self.out / "provenance.csv").unlink()
        with self.assertRaises(FileNotFoundError):
            self.freeze()
        self.assertFalse((self.out / "frozen.json").exists())

    def test_provenance_and_review_must_match_matrix(self):
        self.setup_protocol()
        self.finish_review()
        path = self.out / "provenance.csv"
        rows = csv_rows(path)
        rows[0]["effective_label"] = "1"
        write_csv(path, rows, list(rows[0]))
        with self.assertRaisesRegex(ValueError, "Provenienza incoerente"):
            self.freeze()
        rows[0]["effective_label"] = "0"
        write_csv(path, rows[:-1], list(rows[0]))
        with self.assertRaisesRegex(ValueError, "Provenienza incompleta"):
            self.freeze()
        write_csv(path, rows, list(rows[0]))
        self.review[1]["human_label"] = "0"
        self.write_review()
        with self.assertRaisesRegex(ValueError, "diversa dalla matrice"):
            self.freeze()

    def test_import_review_requires_explicit_correction_and_preserves_proposals(self):
        self.setup_protocol()
        original = (self.proposals / "complete_labels.csv").read_bytes()
        import_review(self.out)  # Only first fixture review is filled.
        self.assertEqual(sum(r["human_confirmed"] == "1" for r in
                             csv_rows(self.out / "provenance.csv")), 1)
        self.review[1].update(human_label="0", human_reason="Synthetic correction",
                              reviewed_by="fixture", reviewed_at="2026-11-13")
        self.write_review()
        unchanged = (self.out / "annotations.csv").read_bytes()
        with self.assertRaisesRegex(ValueError, "corrected_label"):
            import_review(self.out)
        self.assertEqual((self.out / "annotations.csv").read_bytes(), unchanged)
        self.review[1]["corrected_label"] = "0"
        self.write_review()
        import_review(self.out)
        self.assertEqual(self.rows()[1]["Q01"], "0")
        self.assertEqual((self.proposals / "complete_labels.csv").read_bytes(), original)
        self.assertEqual(len(csv_rows(self.proposals / "human_corrections.csv")), 1)
        self.assertEqual(self.freeze()["status"], ASSISTED_STATUS)

    def test_review_types_and_idempotence_preserve_previous_confirmations(self):
        self.setup_protocol()
        self.finish_review()
        labels = csv_rows(self.proposals / "complete_labels.csv")
        self.review.append(dict(**labels[20], human_label="1", corrected_label="", human_reason="Synthetic bulk approval, no independent reading",
                                reviewed_by="fixture", reviewed_at="2026-11-13"))
        self.write_review()
        prov = csv_rows(self.out / "provenance.csv")
        for r in prov:
            r["source"] = "codex_calibration_basename_v2"  # Proposal origin differs from review stage.
        prov[0].update(human_confirmed="1", reviewer="fixture", confirmation_date="2026-11-13",
                       review_type="assisted_confirmation_after_discussion")
        # DictWriter needs the new column also on unconfirmed rows.
        for r in prov:
            r.setdefault("review_type", "not_individually_confirmed")
        write_csv(self.out / "provenance.csv", prov, list(prov[0]))
        old_provenance = dict(prov[0])
        old_review = dict(self.review[0])
        modes = [dict(doc_id=self.review[1]["doc_id"], query_id="Q01", review_type="assisted_confirmation_after_discussion"),
                 dict(doc_id=self.review[2]["doc_id"], query_id="Q01", review_type="assisted_bulk_confirmation")]
        write_json(self.proposals / "final_supervision.json", dict(pair_review_types=modes, new_discussed_pairs=1,
                                                                  new_bulk_pairs=1, new_approved_pairs=2))
        self.assertEqual(import_review(self.out), 2)
        current = csv_rows(self.out / "provenance.csv")
        self.assertEqual(current[0], old_provenance)
        self.assertEqual(csv_rows(self.proposals / "final_review.csv")[0], old_review)
        self.assertEqual(current[10]["review_type"], "assisted_confirmation_after_discussion")
        self.assertEqual(current[20]["review_type"], "assisted_bulk_confirmation")
        counts = read_json(self.proposals / "classification_manifest.json")["counts"]
        self.assertEqual(counts["assisted_confirmation_groups"], dict(calibration=1, discussed=1, bulk=1))
        before = (self.out / "provenance.csv").read_bytes()
        self.assertEqual(import_review(self.out), 0)
        self.assertEqual((self.out / "provenance.csv").read_bytes(), before)

    def test_invalid_review_type_rejected_before_import(self):
        self.setup_protocol()
        write_json(self.proposals / "final_supervision.json", dict(pair_review_types=[
            dict(doc_id=self.review[1]["doc_id"], query_id="Q01", review_type="independently_verified")]))
        before = (self.out / "annotations.csv").read_bytes()
        with self.assertRaisesRegex(ValueError, "Modalita"):
            import_review(self.out)
        self.assertEqual((self.out / "annotations.csv").read_bytes(), before)

    def test_final_and_proposed_positive_counts_remain_distinct(self):
        self.setup_protocol()
        self.review[1].update(human_label="0", corrected_label="0", human_reason="Synthetic correction",
                              reviewed_by="fixture", reviewed_at="2026-11-13")
        self.write_review()
        self.assertEqual(import_review(self.out), 2)
        m = read_json(self.proposals / "classification_manifest.json")
        self.assertEqual(m["counts"]["proposed_positive_by_query"]["Q01"], 11)
        self.assertEqual(m["counts"]["effective_positive_by_query"]["Q01"], 10)
        self.assertEqual(len(csv_rows(self.proposals / "human_corrections.csv")), 1)
        self.assertEqual(import_review(self.out), 0)
        self.assertEqual(len(csv_rows(self.proposals / "human_corrections.csv")), 1)

    def test_batch_resume_and_conflict_preserve_existing_labels(self):
        output = self.out / "codex_proposals"
        write_csv(output / "complete_labels.csv", [],
                  ["doc_id", "query_id", "proposed_label", "confidence", "reason"])
        write_csv(self.out / "provenance.csv", [],
                  ["doc_id", "query_id", "proposed_label", "effective_label", "source", "preexisting_label",
                   "human_confirmed", "reviewer", "confirmation_date", "review_type"])
        records = [dict(id="00_s", mask="0000000000", n="Synthetic title", t="Synthetic text")]
        params = dict(output=output, documents=self.docs, annotations=self.out / "annotations.csv",
                      provenance=self.out / "provenance.csv")
        self.assertEqual(record_batch(1, records, **params), 10)
        baseline = (self.out / "annotations.csv").read_bytes()
        self.assertEqual(record_batch(1, records, **params), 10)
        self.assertEqual((self.out / "annotations.csv").read_bytes(), baseline)
        rows = self.rows()
        rows[0]["Q01"] = "1"
        self.save(rows)
        modified = (self.out / "annotations.csv").read_bytes()
        with self.assertRaisesRegex(ValueError, "Conflitto"):
            record_batch(1, records, **params)
        self.assertEqual((self.out / "annotations.csv").read_bytes(), modified)


if __name__ == "__main__":
    unittest.main()
