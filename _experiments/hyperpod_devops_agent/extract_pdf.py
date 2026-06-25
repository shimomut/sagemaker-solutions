"""Extract text from a PDF into a .txt file alongside it.

Used to make the DevOps Agent docs (PDF) searchable/readable from Claude/grep
without depending on system tools like poppler.
"""
import argparse
import sys
from pathlib import Path

from pypdf import PdfReader


def extract(pdf_path: Path, out_path: Path, page_markers: bool) -> None:
    reader = PdfReader(str(pdf_path))
    total = len(reader.pages)
    with out_path.open("w", encoding="utf-8") as f:
        for i, page in enumerate(reader.pages, start=1):
            if page_markers:
                f.write(f"\n===== PAGE {i}/{total} =====\n")
            f.write(page.extract_text() or "")
            f.write("\n")
            if i % 25 == 0 or i == total:
                print(f"  {pdf_path.name}: {i}/{total} pages", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, nargs="+", help="PDF file(s) to extract")
    parser.add_argument(
        "--no-page-markers",
        action="store_true",
        help="Omit the '===== PAGE N/TOTAL =====' markers between pages.",
    )
    args = parser.parse_args()

    for pdf in args.pdf:
        if not pdf.is_file():
            print(f"skip (not a file): {pdf}", file=sys.stderr)
            continue
        out = pdf.with_suffix(".txt")
        print(f"Extracting {pdf} -> {out}", file=sys.stderr)
        extract(pdf, out, page_markers=not args.no_page_markers)


if __name__ == "__main__":
    main()
