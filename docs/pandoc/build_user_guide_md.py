"""Derive the User Guide Markdown from readme.md for PDF rendering.

`make pdf` builds a single PDF, docs/user-guide.pdf, from the project readme so
the readme stays the one source of truth. The User Guide is the readme with a
few edits that only make sense for a standalone printed document:

  * a pandoc title block (title / subtitle / author) is prepended, so the PDF
    gets tabtabtab's LaTeX title page instead of a bare "tabtabtab" heading;
  * the top-level "# tabtabtab" heading is replaced by an "# Introduction"
    heading (the title block already carries the tabtabtab title), so the intro
    paragraph gets its own numbered section after the contents;
  * the manual "## Contents" section is dropped, because pandoc generates its
    own table of contents for the PDF (toc: true in pdf.yaml);
  * the "## Demo GIFs" section is dropped, because a PDF cannot play animated
    GIFs — the static screenshots in "## Screenshots" carry the same features;
  * the "## Installation" section is dropped, because the User Guide is
    distributed to people who already have tabtabtab installed.

The readme's section headings are all "## " (level two); only the document
title is "# " (level one). Section dropping therefore keys on "## " headings and
runs until the next "## " (or "# ") heading.

Usage:
    python3 docs/pandoc/build_user_guide_md.py readme.md docs/.build/user-guide.md
"""
import sys

TITLE_BLOCK = """\
---
title: "tabtabtab — User Guide"
subtitle: "A faster, smarter command palette for Nuke"
author: "tabtabtab"
---
"""

TITLE_HEADING = "# tabtabtab"
INTRODUCTION_HEADING = "# Introduction"

# Sections (level-two "## " headings) dropped from the printed guide.
DROPPED_SECTION_HEADINGS = {
    "## Contents",
    "## Demo GIFs",
    "## Installation",
}


def is_section_heading(line):
    return line.startswith("## ")


def is_document_title_heading(line):
    return line.startswith("# ") and not line.startswith("## ")


def build_user_guide(readme_text):
    output_lines = [TITLE_BLOCK]
    is_inside_dropped_section = False

    for line in readme_text.splitlines():
        if is_inside_dropped_section:
            # A dropped section runs until the next section (or document title)
            # heading; fall through so that heading is itself processed.
            if is_section_heading(line) or is_document_title_heading(line):
                is_inside_dropped_section = False
            else:
                continue

        if line in DROPPED_SECTION_HEADINGS:
            is_inside_dropped_section = True
            continue

        if line == TITLE_HEADING:
            # The title block already carries the tabtabtab title, so give the
            # intro paragraph its own "Introduction" section.
            output_lines.append(INTRODUCTION_HEADING)
            continue

        output_lines.append(line)

    return "\n".join(output_lines) + "\n"


def main():
    readme_path, output_path = sys.argv[1], sys.argv[2]
    with open(readme_path, encoding="utf-8") as readme_file:
        readme_text = readme_file.read()
    with open(output_path, "w", encoding="utf-8") as output_file:
        output_file.write(build_user_guide(readme_text))


if __name__ == "__main__":
    main()
