"""Renders a Document (see blocks.py) to plain Markdown - the form the
RAG layer will actually chunk and index. See render_pdf.py for the
showcase-facing counterpart, built from the exact same blocks."""

from __future__ import annotations

from data.generators.documents.blocks import (
    BulletList,
    Document,
    Heading,
    PageBreak,
    Paragraph,
    Table,
)


def render_markdown(document: Document) -> str:
    lines: list[str] = [f"# {document.title}", ""]

    for block in document.blocks:
        if isinstance(block, Heading):
            lines.append(f"{'#' * (block.level + 1)} {block.text}")
            lines.append("")
        elif isinstance(block, Paragraph):
            lines.append(block.text)
            lines.append("")
        elif isinstance(block, BulletList):
            marker = "1." if block.ordered else "-"
            for i, item in enumerate(block.items, start=1):
                lines.append(f"{i}. {item}" if block.ordered else f"{marker} {item}")
            lines.append("")
        elif isinstance(block, Table):
            lines.append("| " + " | ".join(block.headers) + " |")
            lines.append("| " + " | ".join("---" for _ in block.headers) + " |")
            for row in block.rows:
                lines.append("| " + " | ".join(row) + " |")
            lines.append("")
        elif isinstance(block, PageBreak):
            lines.append("---")
            lines.append("")

    return "\n".join(lines).strip() + "\n"
