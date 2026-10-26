"""Reading a document as the numbered sections a handler looks up."""

import re
from typing import Any

HEADING = re.compile(r"^## (\d+)\. (.+)$", re.MULTILINE)

Document = dict[str, Any]
Section = dict[str, str]


def read_document(text: str) -> Document:
    """Split a document into its preamble and its numbered sections."""
    headings = list(HEADING.finditer(text))
    if not headings:
        return {"preamble": text.strip(), "sections": []}
    sections = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        sections.append(
            {
                "section": heading.group(1),
                "title": heading.group(2).strip(),
                "text": text[heading.start() : end].strip(),
            }
        )
    return {"preamble": text[: headings[0].start()].strip(), "sections": sections}


def outline(document: Document) -> list[Section]:
    """Return each section's number and title, for a table of contents."""
    return [
        {"section": section["section"], "title": section["title"]}
        for section in document["sections"]
    ]


def find(document: Document, number: str) -> Section:
    """Return one section of a document, or raise KeyError."""
    for section in document["sections"]:
        if section["section"] == number:
            return section
    raise KeyError(number)
