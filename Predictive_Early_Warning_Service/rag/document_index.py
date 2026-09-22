"""
Builds the RAG document index by re-running the real document builder
functions from data/generators/documents/ in-process, rather than
parsing the rendered .md/.pdf files on disk.

Why: every document's real category tags (relevant_issue_categories,
relevant_component_categories) already exist as data on the Document
dataclass returned by each builder - re-running the builders guarantees
the index can never drift from the generator's own logic. This follows
the project's documented "context-window RAG, not vector-database RAG"
convention (confirmed via exploration - no embeddings/vector search
exists anywhere in this project) - retrieval here is a plain dict
lookup by category/vehicle/claim/policy, not similarity search.
"""

from __future__ import annotations

from dataclasses import dataclass

import warranty_config  # noqa: F401  (ensures project root is on sys.path before the imports below)

from data.generators.documents.blocks import Document
from data.generators.documents.boundary_guidelines import build_boundary_guidelines
from data.generators.documents.claim_adjudication_guidelines import build_claim_adjudication_guidelines
from data.generators.documents.claims_history_ncb import build_claims_history_ncb
from data.generators.documents.component_coverage_schedule import build_component_coverage_schedule
from data.generators.documents.driving_behavior_exclusions import build_driving_behavior_exclusions
from data.generators.documents.insurance_policy_certificate import build_insurance_policy_certificate
from data.generators.documents.insurance_policy_data import load_insured_vehicle_policies
from data.generators.documents.insurance_terms import build_insurance_terms
from data.generators.documents.maintenance_compliance import build_maintenance_compliance
from data.generators.documents.master_warranty_policy import build_master_warranty_policy
from data.generators.documents.rider_cover import build_rider_cover_document
from data.generators.documents.surveyor_report import build_surveyor_report
from data.generators.documents.surveyor_report_data import load_claim_investigations


@dataclass(frozen=True)
class IndexedDocument:
    document: Document
    vehicle_id: str | None = None
    insurance_claim_id: str | None = None
    policy_number: str | None = None
    # False for per-claim/per-policy documents (Surveyor Reports,
    # Certificates, NCB Statements) - they're indexed by vehicle_id/
    # claim_id/policy_number below, but deliberately excluded from
    # category-only lookups. Without this, a general "what does
    # ACCIDENT_DAMAGE mean" question (no vehicle/claim given) would pull
    # in all 22 Surveyor Reports just because each is individually
    # tagged ACCIDENT_DAMAGE, flooding the context with noise instead of
    # the one relevant global document (Boundary Guidelines).
    category_searchable: bool = True


class DocumentIndex:
    """In-memory index: category/id -> matching IndexedDocuments.
    Built once at service startup (or on demand for a script), rebuilt
    by calling build_document_index() again if the underlying data
    changes - there is no caching beyond the process's own lifetime,
    matching the fact that source data (claims, policies) can grow."""

    def __init__(self, documents: list[IndexedDocument]) -> None:
        self.documents = documents
        self._by_issue_category: dict[str, list[IndexedDocument]] = {}
        self._by_component_category: dict[str, list[IndexedDocument]] = {}
        self._by_vehicle_id: dict[str, list[IndexedDocument]] = {}
        self._by_claim_id: dict[str, IndexedDocument] = {}
        self._by_policy_number: dict[str, list[IndexedDocument]] = {}

        for entry in documents:
            if entry.category_searchable:
                for issue_category in entry.document.relevant_issue_categories:
                    self._by_issue_category.setdefault(issue_category, []).append(entry)
                for component_category in entry.document.relevant_component_categories:
                    self._by_component_category.setdefault(component_category, []).append(entry)
            if entry.vehicle_id:
                self._by_vehicle_id.setdefault(entry.vehicle_id, []).append(entry)
            if entry.insurance_claim_id:
                self._by_claim_id[entry.insurance_claim_id] = entry
            if entry.policy_number:
                self._by_policy_number.setdefault(entry.policy_number, []).append(entry)

    def by_issue_category(self, issue_category: str) -> list[IndexedDocument]:
        return self._by_issue_category.get(issue_category, [])

    def by_component_category(self, component_category: str) -> list[IndexedDocument]:
        return self._by_component_category.get(component_category, [])

    def by_vehicle_id(self, vehicle_id: str) -> list[IndexedDocument]:
        return self._by_vehicle_id.get(vehicle_id, [])

    def by_claim_id(self, insurance_claim_id: str) -> IndexedDocument | None:
        return self._by_claim_id.get(insurance_claim_id)

    def by_policy_number(self, policy_number: str) -> list[IndexedDocument]:
        return self._by_policy_number.get(policy_number, [])


def build_document_index() -> DocumentIndex:
    entries: list[IndexedDocument] = []

    # Global documents - one instance each, tagged against whatever
    # categories their own builder already declares as relevant.
    for builder in (
        build_master_warranty_policy,
        build_component_coverage_schedule,
        build_driving_behavior_exclusions,
        build_maintenance_compliance,
        build_claim_adjudication_guidelines,
        build_boundary_guidelines,
        build_insurance_terms,
        build_rider_cover_document,
    ):
        entries.append(IndexedDocument(document=builder()))

    # Per-claim documents (Surveyor Reports) - indexed by vehicle_id and
    # insurance_claim_id for direct lookup, plus their own declared
    # category tags for general "what does a claim for issue X look
    # like" retrieval.
    for investigation in load_claim_investigations():
        document = build_surveyor_report(investigation)
        entries.append(
            IndexedDocument(
                document=document,
                vehicle_id=str(investigation.claim["vehicle_id"]),
                insurance_claim_id=str(investigation.claim["insurance_claim_id"]),
                category_searchable=False,
            )
        )

    # Per-policy documents (Certificate + NCB Statement) - indexed by
    # vehicle_id and policy_number.
    for policy, claims in load_insured_vehicle_policies():
        certificate = build_insurance_policy_certificate(policy)
        entries.append(
            IndexedDocument(
                document=certificate,
                vehicle_id=policy.vehicle_id,
                policy_number=policy.policy_number,
                category_searchable=False,
            )
        )
        ncb_statement = build_claims_history_ncb(policy, claims)
        entries.append(
            IndexedDocument(
                document=ncb_statement,
                vehicle_id=policy.vehicle_id,
                policy_number=policy.policy_number,
                category_searchable=False,
            )
        )

    return DocumentIndex(entries)
