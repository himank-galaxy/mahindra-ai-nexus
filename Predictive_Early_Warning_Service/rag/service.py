"""
Orchestrates one RAG turn: retrieve matching document context -> assemble
prompt -> call the LLM -> return the answer. Mirrors
Predictive_Early_Warning_Service/copilot/service.py::ask_copilot.
"""

from __future__ import annotations

from rag.document_index import DocumentIndex
from rag.llm_client import ask
from rag.prompts import SYSTEM_PROMPT
from rag.retrieval import retrieve_context


class NoMatchingDocumentsError(RuntimeError):
    """Raised when no document in the index matches the given filters."""


def ask_warranty_docs(
    index: DocumentIndex,
    question: str,
    *,
    issue_category: str | None = None,
    component_category: str | None = None,
    vehicle_id: str | None = None,
    claim_id: str | None = None,
) -> str:
    context = retrieve_context(
        index,
        issue_category=issue_category,
        component_category=component_category,
        vehicle_id=vehicle_id,
        claim_id=claim_id,
    )

    if not context:
        raise NoMatchingDocumentsError(
            "No documents matched the given issue_category/component_category/vehicle_id/claim_id filters."
        )

    # Same single-system-message constraint already confirmed against
    # the real LLM gateway elsewhere in this project.
    messages = [
        {
            "role": "system",
            "content": f"{SYSTEM_PROMPT}\n\nRETRIEVED DOCUMENTS:\n\n{context}",
        },
        {"role": "user", "content": question},
    ]

    return ask(messages)
