"""Renders a Document (see blocks.py) to a real PDF, for showcasing -
built from the exact same blocks as render_markdown.py's RAG-facing
output, so the two can never disagree about content."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak as RLPageBreak,
    Paragraph as RLParagraph,
    SimpleDocTemplate,
    Spacer,
    Table as RLTable,
    TableStyle,
)

from data.generators.documents.blocks import (
    BulletList,
    Document,
    Heading,
    PageBreak,
    Paragraph,
    Table,
)

_STYLES = getSampleStyleSheet()

_TITLE_STYLE = ParagraphStyle(
    "DocTitle", parent=_STYLES["Title"], fontSize=16, spaceAfter=10, textColor=colors.HexColor("#c8102e")
)
_H2_STYLE = ParagraphStyle("H2", parent=_STYLES["Heading2"], fontSize=12.5, spaceBefore=14, spaceAfter=6)
_H3_STYLE = ParagraphStyle("H3", parent=_STYLES["Heading3"], fontSize=11, spaceBefore=10, spaceAfter=4)
_BODY_STYLE = ParagraphStyle("Body", parent=_STYLES["BodyText"], fontSize=9.5, leading=13, spaceAfter=6)
_BULLET_STYLE = ParagraphStyle("Bullet", parent=_STYLES["BodyText"], fontSize=9.5, leading=13)


def _heading_style(level: int) -> ParagraphStyle:
    return _H2_STYLE if level <= 2 else _H3_STYLE


def render_pdf(document: Document, output_path: str | Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        title=document.title,
    )

    story = [RLParagraph(document.title, _TITLE_STYLE), Spacer(1, 4 * mm)]

    for block in document.blocks:
        if isinstance(block, Heading):
            story.append(RLParagraph(block.text, _heading_style(block.level)))
        elif isinstance(block, Paragraph):
            story.append(RLParagraph(block.text, _BODY_STYLE))
        elif isinstance(block, BulletList):
            items = [
                ListItem(RLParagraph(item, _BULLET_STYLE), value=i if block.ordered else None)
                for i, item in enumerate(block.items, start=1)
            ]
            story.append(
                ListFlowable(
                    items,
                    bulletType="1" if block.ordered else "bullet",
                    leftIndent=14,
                    spaceAfter=6,
                )
            )
        elif isinstance(block, Table):
            header_style = ParagraphStyle("TableHeader", parent=_BODY_STYLE, fontName="Helvetica-Bold")
            data = [list(block.headers)] + [list(row) for row in block.rows]
            wrapped = [
                [
                    RLParagraph(str(cell), header_style if row_index == 0 else _BODY_STYLE)
                    for cell in row
                ]
                for row_index, row in enumerate(data)
            ]
            table = RLTable(wrapped, repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                        ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            story.append(table)
            story.append(Spacer(1, 4 * mm))
        elif isinstance(block, PageBreak):
            story.append(RLPageBreak())

    doc.build(story)
