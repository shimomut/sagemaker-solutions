"""Extract a page range of an AWS documentation PDF into Markdown.

The AWS docs PDFs embed useful font metadata that plain text extraction throws
away:

* ``AmazonEmber-Bold`` at 14pt/16pt marks section headings.
* ``AmazonEmberMono-Regular`` at 10pt marks code blocks.
* ``AmazonEmberMono-Regular`` at 12pt marks inline code.
* 8pt text is the running page header and footer.

This script walks the text runs with their coordinates and fonts, rebuilds
lines, and classifies each line so the output keeps headings, fenced code
blocks, lists, and inline code. Heading levels come from the PDF outline
(bookmarks), which gives the real nesting depth rather than a guess based on
font size.

Usage:
    python3 scripts/extract_pdf_docs.py \
        --pdf docs/sagemaker-dg.pdf \
        --first-page 2784 --last-page 2849 \
        --output docs/ray-on-hyperpod.md

Known limitation: tables are flattened. Cells on the same visual line are
joined with " | ", but a cell whose text wraps onto several lines becomes
several rows. The result is readable but is not a valid Markdown table.
"""

import argparse
import re
import sys
from dataclasses import dataclass, field

from pypdf import PdfReader

# Font sizes used by the AWS docs PDF template.
HEADER_FOOTER_MAX_SIZE = 9.0
CODE_SIZE = 10.0
BODY_SIZE = 12.0

# Average glyph width as a fraction of the font size, used only to estimate
# where a run ends so we can spot the wide gaps between table columns.
WIDTH_RATIO_MONO = 0.60
WIDTH_RATIO_SANS = 0.50

# A horizontal gap wider than this many points means a new table column.
COLUMN_GAP = 20.0

# Two runs are on the same line if their baselines are within this many points.
LINE_TOLERANCE = 1.5

BULLET_CHARS = "•◦‣⁃-"
CALLOUTS = {"Note", "Important", "Warning", "Tip"}

# Ligatures and typographic characters that the PDF uses but Markdown readers
# are happier without.
REPLACEMENTS = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "–": "-",
    "—": "--",
    " ": " ",
}


def clean(text):
    for src, dst in REPLACEMENTS.items():
        text = text.replace(src, dst)
    return text


@dataclass
class Run:
    """A single text-showing operation with its position and font."""

    x: float
    y: float
    text: str
    font: str
    size: float

    @property
    def mono(self):
        return "Mono" in self.font

    @property
    def bold(self):
        return "Bold" in self.font

    @property
    def width(self):
        ratio = WIDTH_RATIO_MONO if self.mono else WIDTH_RATIO_SANS
        return len(self.text) * self.size * ratio


@dataclass
class Line:
    """Runs sharing a baseline, ordered left to right."""

    y: float
    page: int
    runs: list = field(default_factory=list)

    @property
    def x(self):
        return self.runs[0].x

    @property
    def size(self):
        return max(run.size for run in self.runs)

    @property
    def is_code(self):
        return all(run.mono for run in self.runs) and self.size <= CODE_SIZE

    @property
    def is_bold(self):
        return all(run.bold for run in self.runs)

    @property
    def plain(self):
        return "".join(run.text for run in self.runs).strip()


def read_runs(page):
    """Collect the text runs of one page, dropping the header and footer.

    Positions are converted to device space, because the page header, body, and
    footer each live in their own coordinate system. pypdf also reports some
    runs with a zeroed text matrix; those are continuations of the run before
    them, so they are placed just to its right instead of at the origin.
    """
    runs = []

    def visitor(text, cm, tm, font_dict, font_size):
        if not text or not text.strip():
            return
        size = float(font_size or 0)
        if size <= HEADER_FOOTER_MAX_SIZE:
            return  # running header / footer
        font = str((font_dict or {}).get("/BaseFont", "")).split("+")[-1]

        if tm[4] == 0 and tm[5] == 0 and runs:
            previous = runs[-1]
            x, y = previous.x + previous.width, previous.y
        else:
            x = cm[0] * tm[4] + cm[2] * tm[5] + cm[4]
            y = cm[1] * tm[4] + cm[3] * tm[5] + cm[5]

        runs.append(Run(x=float(x), y=float(y), text=clean(text), font=font, size=size))

    page.extract_text(visitor_text=visitor)
    return runs


def group_lines(runs, page_number):
    """Group runs into lines, ordered top to bottom (device y grows upward)."""
    lines = []
    for run in sorted(runs, key=lambda r: (-r.y, r.x)):
        if lines and abs(run.y - lines[-1].y) <= LINE_TOLERANCE:
            lines[-1].runs.append(run)
        else:
            lines.append(Line(y=run.y, page=page_number, runs=[run]))
    for line in lines:
        line.runs.sort(key=lambda r: r.x)
    return lines


def build_outline_index(reader, first_page, last_page):
    """Map (page, normalized title) -> heading depth from the PDF bookmarks."""
    index = {}

    def normalize(title):
        return re.sub(r"\s+", " ", clean(title)).strip().lower()

    def walk(items, depth):
        for item in items:
            if isinstance(item, list):
                walk(item, depth + 1)
                continue
            try:
                page = reader.get_page_number(item.page) + 1
            except Exception:
                continue
            if first_page <= page <= last_page:
                index.setdefault((page, normalize(item.title)), depth)

    walk(reader.outline, 0)
    if not index:
        return {}, 0
    base_depth = min(index.values())
    return index, base_depth


def heading_level(line, outline, base_depth):
    """Return the Markdown heading level for a line, or None if it is not one."""
    if not line.is_bold:
        return None
    title = re.sub(r"\s+", " ", line.plain).lower()
    for page in (line.page, line.page - 1, line.page + 1):
        depth = outline.get((page, title))
        if depth is not None:
            return depth - base_depth + 1
    # Bold lines that are not bookmarked (for example "Topics") are not
    # headings, but a large bold line still is - the outline occasionally
    # omits one.
    if line.size >= 14.0:
        return None if len(line.plain) > 120 else 3
    return None


def render_body(line):
    """Render a body line, wrapping monospace runs in backticks."""
    parts = []
    previous = None
    for run in line.runs:
        if previous is not None:
            gap = run.x - (previous.x + previous.width)
            if gap > COLUMN_GAP:
                parts.append(" | ")
        if run.mono:
            stripped = run.text.strip()
            if stripped:
                leading = " " if run.text[:1].isspace() else ""
                trailing = " " if run.text[-1:].isspace() else ""
                parts.append(f"{leading}`{stripped}`{trailing}")
        else:
            parts.append(run.text)
        previous = run
    return re.sub(r"``+", "`", "".join(parts)).strip()


def bullet_indent(x):
    if x < 10:
        return 0
    if x < 30:
        return 1
    return 2


def guess_language(code_lines):
    body = "\n".join(code_lines)
    if re.search(r"^\s*(apiVersion|kind|metadata|spec):", body, re.M):
        return "yaml"
    if re.search(r"^\s*(kubectl|helm|aws|eksctl|pip|export|ray|curl|git|sudo|\$)\b", body, re.M):
        return "bash"
    if re.search(r"^\s*(import|from|def|class|@ray|print\()", body, re.M):
        return "python"
    if body.lstrip().startswith("{") and '"' in body:
        return "json"
    return ""


class MarkdownWriter:
    """Accumulates blocks and emits Markdown with sane blank lines."""

    def __init__(self):
        self.blocks = []
        self._paragraph = []
        self._code = []

    def _flush_paragraph(self):
        if self._paragraph:
            self.blocks.append(" ".join(self._paragraph))
            self._paragraph = []

    def _flush_code(self):
        if self._code:
            language = guess_language(self._code)
            body = "\n".join(line.rstrip() for line in self._code).strip("\n")
            self.blocks.append(f"```{language}\n{body}\n```")
            self._code = []

    def flush(self):
        self._flush_paragraph()
        self._flush_code()

    def heading(self, level, text):
        self.flush()
        self.blocks.append(f"{'#' * min(level, 6)} {text}")

    def paragraph_break(self):
        self._flush_paragraph()

    def add_text(self, text):
        self._flush_code()
        self._paragraph.append(text)

    def add_block(self, text):
        self.flush()
        self.blocks.append(text)

    def add_code(self, text):
        self._flush_paragraph()
        self._code.append(text)

    def render(self):
        self.flush()
        return "\n\n".join(self.blocks) + "\n"


def convert(lines, outline, base_depth):
    writer = MarkdownWriter()
    previous = None
    started = False

    for line in lines:
        text = line.plain
        if not text:
            continue

        if not started:
            # The first page usually opens with the tail of the previous
            # section; skip everything before the first real heading.
            if heading_level(line, outline, base_depth) is None:
                continue
            started = True

        page_break = previous is not None and line.page != previous.page
        # Device y grows upward, so the drop from one line to the next is positive.
        gap = None if previous is None or page_break else previous.y - line.y

        if line.is_code:
            # A code block may straddle a page boundary; keep it open when the
            # previous line was code too.
            if not (previous is not None and previous.is_code):
                writer._flush_paragraph()
            if gap is not None and gap > 1.8 * CODE_SIZE * 1.5:
                writer._flush_code()
            raw = "".join(run.text for run in line.runs).rstrip()
            writer.add_code(raw)
            previous = line
            continue

        writer._flush_code()

        level = heading_level(line, outline, base_depth)
        if level is not None:
            writer.heading(level, text)
            previous = line
            continue

        rendered = render_body(line)
        if not rendered:
            continue

        if line.is_bold and text in CALLOUTS:
            writer.add_block(f"**{text}**")
            previous = line
            continue

        if line.is_bold and line.size <= BODY_SIZE:
            writer.add_block(f"**{rendered}**")
            previous = line
            continue

        first = line.runs[0].text.strip()
        bullet = first and first[0] in BULLET_CHARS and len(first) <= 2
        numbered = bool(re.match(r"^\d+\.$", first))

        if bullet or numbered:
            writer.paragraph_break()
            rest = render_body(Line(line.y, line.page, line.runs[1:])) if len(line.runs) > 1 else ""
            marker = "-" if bullet else first
            writer.add_text(f"{'  ' * bullet_indent(line.x)}{marker} {rest}".rstrip())
            previous = line
            continue

        if gap is not None and gap > 1.35 * BODY_SIZE * 1.5:
            writer.paragraph_break()
        elif page_break and previous is not None and previous.plain.endswith((".", ":", "?", "!")):
            writer.paragraph_break()

        writer.add_text(rendered)
        previous = line

    return writer.render()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--pdf", required=True, help="Path to the source PDF")
    parser.add_argument("--first-page", type=int, required=True, help="First page, 1-based inclusive")
    parser.add_argument("--last-page", type=int, required=True, help="Last page, 1-based inclusive")
    parser.add_argument("--output", required=True, help="Path of the Markdown file to write")
    parser.add_argument("--source-note", default=None, help="Attribution line added at the top")
    args = parser.parse_args(argv)

    reader = PdfReader(args.pdf)
    total = len(reader.pages)
    if not 1 <= args.first_page <= args.last_page <= total:
        parser.error(f"page range must be within 1..{total}")

    outline, base_depth = build_outline_index(reader, args.first_page, args.last_page)
    if not outline:
        print("warning: no PDF bookmarks in this range; headings may be missed", file=sys.stderr)

    lines = []
    for number in range(args.first_page, args.last_page + 1):
        page = reader.pages[number - 1]
        lines.extend(group_lines(read_runs(page), number))

    # Shift x so the body left margin sits at 0, which makes the indentation
    # thresholds independent of the page margins.
    if lines:
        left = min(run.x for line in lines for run in line.runs)
        for line in lines:
            for run in line.runs:
                run.x -= left

    markdown = convert(lines, outline, base_depth)

    note = args.source_note or (
        f"Extracted from `{args.pdf}` pages {args.first_page}-{args.last_page} "
        f"by `scripts/extract_pdf_docs.py`. Do not edit by hand."
    )
    header = f"<!-- {note} -->\n\n"

    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(header + markdown)

    print(f"wrote {args.output} ({len(markdown.splitlines())} lines)")


if __name__ == "__main__":
    main()
