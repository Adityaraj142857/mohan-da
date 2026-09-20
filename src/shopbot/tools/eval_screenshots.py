"""Owner-run real-world OCR evaluation (SPEC 15.4). Required before trusting
OCR: run against ~20 real, redacted screenshots with an optional
labels.csv (filename,amount,utr,status) and print per-field accuracy.

Usage: python -m shopbot.tools.eval_screenshots <folder>
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from shopbot.verify.screenshot.extract import extract_fields
from shopbot.verify.screenshot.ocr.factory import make_ocr_engine

IMAGE_EXTS = {".png", ".jpg", ".jpeg"}


def load_labels(folder: Path) -> dict[str, dict]:
    labels_path = folder / "labels.csv"
    if not labels_path.exists():
        return {}
    with labels_path.open(newline="", encoding="utf-8") as f:
        return {row["filename"]: row for row in csv.DictReader(f)}


def run_eval(folder: str, ocr_engine_name: str = "rapidocr") -> None:
    folder_path = Path(folder)
    labels = load_labels(folder_path)
    engine = make_ocr_engine(ocr_engine_name)

    images = sorted(p for p in folder_path.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if not images:
        print(f"No images found in {folder}")
        return

    totals = {"amount": 0, "utr": 0, "status": 0}
    correct = {"amount": 0, "utr": 0, "status": 0}
    failures = []

    for path in images:
        image_bytes = path.read_bytes()
        ocr_result = engine.run(image_bytes)
        expected_amount = labels.get(path.name, {}).get("amount", "")
        extracted = extract_fields(ocr_result.full_text, expected_amount or "0.00")

        label = labels.get(path.name)
        if label:
            if label.get("amount"):
                totals["amount"] += 1
                if extracted.amount_matches_expected:
                    correct["amount"] += 1
                else:
                    failures.append(f"{path.name}: amount expected {label['amount']}, got {extracted.amount_candidates}")
            if label.get("utr"):
                totals["utr"] += 1
                if extracted.utr == label["utr"]:
                    correct["utr"] += 1
                else:
                    failures.append(f"{path.name}: utr expected {label['utr']}, got {extracted.utr}")
            if label.get("status"):
                totals["status"] += 1
                if extracted.status == label["status"]:
                    correct["status"] += 1
                else:
                    failures.append(f"{path.name}: status expected {label['status']}, got {extracted.status}")
        else:
            print(f"{path.name}: OCR confidence={ocr_result.mean_confidence:.2f} amount={extracted.amount_candidates} "
                  f"utr={extracted.utr} status={extracted.status}")

    if totals["amount"] or totals["utr"] or totals["status"]:
        print("\n--- Accuracy ---")
        for field in ("amount", "utr", "status"):
            if totals[field]:
                pct = 100.0 * correct[field] / totals[field]
                print(f"{field}: {correct[field]}/{totals[field]} = {pct:.1f}% (target >= 90%)")
        if failures:
            print("\n--- Failures ---")
            for f in failures:
                print(f" - {f}")
    else:
        print("\nNo labels.csv found (or no labelled fields) — printed raw extraction above.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    run_eval(sys.argv[1])
