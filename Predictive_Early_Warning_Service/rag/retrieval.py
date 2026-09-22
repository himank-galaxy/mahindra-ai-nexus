"""
Turns a DocumentIndex lookup into a plain-English context block for the
LLM - the same "build a deterministic case file from structured data"
pattern already used in
Predictive_Early_Warning_Service/copilot/context_builder.py, applied to
documents instead of a causal investigation.
"""

from __future__ import annotations

from data.generators.documents.render_markdown import render_markdown
from rag.document_index import DocumentIndex, IndexedDocument


def _dedupe(entries: list[IndexedDocument]) -> list[IndexedDocument]:
    seen: set[int] = set()
    unique: list[IndexedDocument] = []
    for entry in entries:
        key = id(entry.document)
        if key not in seen:
            seen.add(key)
            unique.append(entry)
    return unique


def retrieve_context(
    index: DocumentIndex,
    *,
    issue_category: str | None = None,
    component_category: str | None = None,
    vehicle_id: str | None = None,
    claim_id: str | None = None,
) -> str:
    """
    Returns a concatenated plain-text context block of every matching
    document's real rendered content - nothing here is generated, only
    retrieved and joined. An empty string means no match was found (the
    caller/LLM must say so honestly, not invent an answer).
    """

    matches: list[IndexedDocument] = []

    if issue_category:
        matches += index.by_issue_category(issue_category)
    if component_category:
        matches += index.by_component_category(component_category)
    if vehicle_id:
        matches += index.by_vehicle_id(vehicle_id)
    if claim_id:
        found = index.by_claim_id(claim_id)
        if found:
            matches.append(found)

    matches = _dedupe(matches)

    if not matches:
        return ""

    sections = []
    for entry in matches:
        sections.append(f"=== {entry.document.title} ===\n\n{render_markdown(entry.document)}")

    return "\n\n".join(sections)
