"""Extraction and indexing of the store's policy manual.

The manual is 8 pages long (~11k characters). Instead of embeddings and a vector store,
it is split by the document's own numbered sections and the agent looks up a section by
topic. For a document this size, with a clear structure, section lookup is exact, free
and easy to audit.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from pypdf import PdfReader

PDF_PATH = Path(__file__).parent / "data" / "políticas_da_loja.pdf"

# Topic key used by the agent -> section number in the manual.
SECTIONS = {
    "about_store": 1,  # who we are, address, phone, what the store does (not) sell
    "opening_hours": 2,
    "payment": 3,  # payment methods, PIX discount, installments
    "returns_and_exchanges": 4,
    "shipping": 5,  # shipping fees, delivery times, tracking
    "promotions": 6,  # promotion calendar and rules
    "customer_service": 7,  # service guidelines and special situations
    "warranty": 8,
    "privacy": 9,  # LGPD
}

_NOISE = re.compile(r"^\s*(Página \d+|Empório da Música Manual de Políticas e Procedimentos)\s*$")
_HEADING = re.compile(r"^(\d{1,2})\. (.+)$")


@lru_cache(maxsize=1)
def manual_text() -> str:
    pages = PdfReader(PDF_PATH).pages[1:]  # page 1 is the cover
    lines = []
    for page in pages:
        for line in page.extract_text(extraction_mode="layout").splitlines():
            line = re.sub(r"[ \t]+", " ", line).strip()
            if line and not _NOISE.match(line):
                lines.append(line)
    return "\n".join(lines)


@lru_cache(maxsize=1)
def manual_sections() -> dict[int, str]:
    """Splits the manual into its top-level sections (1. ..., 2. ..., ...)."""
    sections: dict[int, list[str]] = {}
    current = 0
    for line in manual_text().splitlines():
        heading = _HEADING.match(line)
        # Only the next section number counts as a heading; this avoids mistaking
        # numbered lists inside a section (e.g. "2. Entendimento" in section 7.2).
        if heading and int(heading.group(1)) == current + 1:
            current += 1
        if current:
            sections.setdefault(current, []).append(line)
    return {number: "\n".join(lines) for number, lines in sections.items()}


def get_policy(section: str) -> str:
    number = SECTIONS.get(section)
    if number is None:
        return f"Unknown section. Options: {', '.join(SECTIONS)}."
    return manual_sections().get(number, "Section not found in the manual.")


if __name__ == "__main__":
    for key, number in SECTIONS.items():
        text = get_policy(key)
        print(f"== {key} (section {number}, {len(text)} chars) == {text.splitlines()[0]}")
    print()
    print(get_policy("opening_hours"))
