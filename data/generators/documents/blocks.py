"""
Shared content model for synthetic policy/insurance documents.

A document is built once as a list of simple content blocks (heading,
paragraph, bullet list, table) - never as a raw Markdown or PDF string
directly. render_markdown.py and render_pdf.py both consume the same
block list, so the Markdown version (what the RAG layer indexes) and the
PDF version (for showcasing) can never drift apart from each other.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Heading:
    text: str
    level: int = 1  # 1 = document title, 2 = section, 3 = subsection


@dataclass(frozen=True)
class Paragraph:
    text: str


@dataclass(frozen=True)
class BulletList:
    items: tuple[str, ...]
    ordered: bool = False


@dataclass(frozen=True)
class Table:
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class PageBreak:
    pass


Block = Heading | Paragraph | BulletList | Table | PageBreak


@dataclass(frozen=True)
class Document:
    """One generated document: its blocks, plus the metadata needed to
    name/file it and to keep it joinable back to the structured data
    (model name, document type, and - for RAG scoping - which issue
    categories / component categories it's actually relevant to)."""

    doc_type: str  # e.g. "master_warranty_policy"
    title: str
    blocks: tuple[Block, ...]
    vehicle_model: str | None = None  # None for global documents
    relevant_component_categories: tuple[str, ...] = field(default_factory=tuple)
    relevant_issue_categories: tuple[str, ...] = field(default_factory=tuple)
