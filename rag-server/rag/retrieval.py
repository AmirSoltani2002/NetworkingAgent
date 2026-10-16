import logging
import re
import time
from uuid import UUID

from sqlalchemy import func, select, text

from .errors import ServiceError
from .models import Device, DeviceDocument, Document, DocumentChunk, Issue, IssueEvidence
from .services import chunk_json, device_json, issue_json, require

log = logging.getLogger("rag")


def rrf(rankings, k=60):
    scores = {}
    for ranking in rankings:
        for rank, identifier in enumerate(dict.fromkeys(ranking), 1):
            scores[identifier] = scores.get(identifier, 0.0) + 1.0 / (k + rank)
    return scores


class RetrievalService:
    def __init__(self, database, settings, embeddings, reranker=None):
        self.db = database
        self.settings = settings
        self.embeddings = embeddings
        self.reranker = reranker

    def resolve_device(self, session, request):
        if request.device_id:
            device = require(session, Device, request.device_id)
            if (request.device_name and device.name.casefold() != request.device_name.casefold()) or (
                request.device_model and device.model.casefold() != request.device_model.casefold()
            ):
                raise ServiceError(422, "DEVICE_FILTER_CONFLICT", "Device ID and name/model filters disagree")
            return device
        statement = select(Device)
        if request.device_name:
            statement = statement.where(func.lower(Device.name) == request.device_name.lower())
        else:
            # SQL exact-substring candidates, followed by deterministic word-boundary matching.
            statement = statement.where(func.strpos(func.lower(request.query), func.lower(Device.name)) > 0)
        if request.device_model:
            statement = statement.where(func.lower(Device.model) == request.device_model.lower())
        candidates = session.scalars(statement.order_by(Device.id).limit(101)).all()
        if not request.device_name:
            candidates = [
                row
                for row in candidates
                if re.search(r"(?<!\w)" + re.escape(row.name) + r"(?!\w)", request.query, re.IGNORECASE)
            ]
        if len(candidates) > 1:
            raise ServiceError(
                409,
                "AMBIGUOUS_DEVICE",
                "Specify device_id to disambiguate the device",
                {"candidates": [device_json(row) for row in candidates[:20]]},
            )
        if (request.device_name or request.device_model) and not candidates:
            raise ServiceError(404, "DEVICE_NOT_FOUND", "No deterministically matching device was found")
        return candidates[0] if candidates else None

    def document_scope(self, device_id, request):
        clauses = [Document.status == "ready"]
        if device_id:
            clauses.append(
                Document.id.in_(
                    select(DeviceDocument.document_id).where(DeviceDocument.device_id == device_id)
                )
            )
        if request.document_type:
            clauses.append(func.lower(Document.document_type) == request.document_type.lower())
        if request.document_ids is not None:
            clauses.append(Document.id.in_(request.document_ids))
        return clauses

    def search(self, request, request_id=None):
        started = time.monotonic()
        vector = self.embeddings.query(request.query)
        limit = self.settings.candidate_count
        with self.db.session() as session:
            device = self.resolve_device(session, request)
            device_id = device.id if device else None
            if request.document_ids:
                found = set(
                    session.scalars(select(Document.id).where(Document.id.in_(request.document_ids))).all()
                )
                if found != set(request.document_ids):
                    raise ServiceError(404, "DOCUMENT_NOT_FOUND", "One or more document IDs do not exist")
            session.execute(text("SET LOCAL hnsw.iterative_scan = 'strict_order'"))
            session.execute(text(f"SET LOCAL hnsw.ef_search = {min(1000, limit * 2)}"))
            issue_filter = []
            if device_id:
                issue_filter.append(Issue.device_id == device_id)
            if request.issue_category:
                issue_filter.append(func.lower(Issue.category) == request.issue_category.lower())
            issue_distance = Issue.embedding.cosine_distance(vector)
            issue_vector = session.execute(
                select(Issue, (1 - issue_distance).label("similarity"))
                .where(*issue_filter, issue_distance <= 1 - self.settings.issue_similarity_threshold)
                .order_by(issue_distance, Issue.id)
                .limit(limit)
            ).all()
            issue_text = (
                Issue.title + " " + Issue.symptoms + " " + Issue.possible_cause + " " + Issue.description
            )
            issue_tsv = func.to_tsvector("english", issue_text)
            query = func.websearch_to_tsquery("english", request.query)
            issue_rank = func.ts_rank_cd(issue_tsv, query)
            issue_keyword = session.execute(
                select(Issue, issue_rank.label("rank"))
                .where(*issue_filter, issue_tsv.op("@@")(query))
                .order_by(issue_rank.desc(), Issue.id)
                .limit(limit)
            ).all()
            issue_scores = rrf(
                [[row.id for row, _ in issue_vector], [row.id for row, _ in issue_keyword]],
                self.settings.rrf_k,
            )
            issue_rows = {row.id: row for row, _ in [*issue_vector, *issue_keyword]}
            issue_similarities = {row.id: float(score) for row, score in issue_vector}
            issue_keywords = {row.id: float(score) for row, score in issue_keyword}
            matched_ids = sorted(
                issue_scores, key=lambda identifier: (-issue_scores[identifier], str(identifier))
            )[:10]
            matched = [
                dict(
                    issue_json(issue_rows[identifier]),
                    scores={
                        "rrf_score": issue_scores[identifier],
                        "vector_similarity": issue_similarities.get(identifier),
                        "keyword_rank": issue_keywords.get(identifier),
                    },
                )
                for identifier in matched_ids
            ]

            scope = self.document_scope(device_id, request)
            base = (
                select(DocumentChunk, Document)
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(*scope)
            )
            distance = DocumentChunk.embedding.cosine_distance(vector)
            direct_vector = session.execute(
                base.add_columns((1 - distance).label("similarity"))
                .where(distance <= 1 - self.settings.similarity_threshold)
                .order_by(distance, DocumentChunk.id)
                .limit(limit)
            ).all()
            tsv = func.to_tsvector("english", DocumentChunk.content)
            keyword_score = func.ts_rank_cd(tsv, query)
            direct_keyword = session.execute(
                base.add_columns(keyword_score.label("keyword_rank"))
                .where(tsv.op("@@")(query))
                .order_by(keyword_score.desc(), DocumentChunk.id)
                .limit(limit)
            ).all()
            linked = []
            supported = []
            if matched_ids:
                linked = session.execute(
                    base.add_columns(IssueEvidence.issue_id, IssueEvidence.evidence_type)
                    .join(IssueEvidence, IssueEvidence.chunk_id == DocumentChunk.id)
                    .where(IssueEvidence.issue_id.in_(matched_ids))
                    .order_by(DocumentChunk.chunk_index, DocumentChunk.id)
                    .limit(limit)
                ).all()
                issue_devices = {issue_rows[identifier].device_id for identifier in matched_ids}
                supported = session.execute(
                    base.add_columns((1 - distance).label("similarity"))
                    .where(
                        Document.id.in_(
                            select(DeviceDocument.document_id).where(
                                DeviceDocument.device_id.in_(issue_devices)
                            )
                        ),
                        distance <= 1 - self.settings.similarity_threshold,
                    )
                    .order_by(distance, DocumentChunk.id)
                    .limit(limit)
                ).all()

            streams = {
                "document_vector": direct_vector,
                "document_fts": direct_keyword,
                "issue_evidence": linked,
                "issue_document_vector": supported,
            }
            candidates = {}
            rankings = []
            for method, rows in streams.items():
                ranking = []
                for row in rows:
                    chunk, document = row[:2]
                    ranking.append(chunk.id)
                    if chunk.id not in candidates:
                        candidates[chunk.id] = dict(
                            chunk_json(chunk, document),
                            matched_issue_ids=[],
                            evidence_types={},
                            scores={},
                            methods=[],
                        )
                    item = candidates[chunk.id]
                    if method not in item["methods"]:
                        item["methods"].append(method)
                    if method == "issue_evidence":
                        identifier = str(row[2])
                        if identifier not in item["matched_issue_ids"]:
                            item["matched_issue_ids"].append(identifier)
                        item["evidence_types"][identifier] = row[3]
                    else:
                        item["scores"][method] = float(row[2])
                rankings.append(ranking)
            fused = rrf(rankings, self.settings.rrf_k)
            identifiers = sorted(fused, key=lambda identifier: (-fused[identifier], str(identifier)))[:limit]
            items = [candidates[identifier] for identifier in identifiers]
            for identifier, item in zip(identifiers, items):
                item["score"] = fused[identifier]
                item["scores"]["rrf_score"] = fused[identifier]
                item["retrieval_method"] = "hybrid_rrf"
            if self.reranker and items:
                try:
                    reranked = self.reranker.scores(request.query, [item["content"] for item in items])
                    if len(reranked) != len(items):
                        raise ValueError()
                except Exception:
                    raise ServiceError(
                        503, "RERANKER_FAILED", "The local reranker could not score retrieval candidates"
                    ) from None
                for item, score in zip(items, reranked):
                    item["scores"]["reranker_score"] = score
                    item["retrieval_method"] = "hybrid_rrf_reranked"
                items.sort(
                    key=lambda item: (-item["scores"]["reranker_score"], -item["score"], item["chunk_id"])
                )
            items = items[: request.top_k or self.settings.retrieval_top_k]
            document_ids = {UUID(item["document_id"]) for item in items}
            related = session.execute(
                select(DeviceDocument.document_id, Device)
                .join(Device)
                .where(DeviceDocument.document_id.in_(document_ids))
            ).all()
            for item in items:
                item["devices"] = [
                    device_json(row)
                    for document_id, row in related
                    if str(document_id) == item["document_id"]
                ]
            result = {
                "device_id": str(device_id) if device_id else None,
                "device": device_json(device) if device else None,
                "matched_issues": matched,
                "results": items,
                "score_semantics": "Ranking scores, not confidence probabilities",
                "embedding": self.settings.embedding_contract,
            }
        log.info(
            "retrieval_complete",
            extra={
                "event": "retrieval_complete",
                "request_id": request_id,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "device_id": result["device_id"],
                "issue_category": request.issue_category,
                "document_type": request.document_type,
                "document_ids_filter": [str(identifier) for identifier in request.document_ids or []],
                "top_k": request.top_k or self.settings.retrieval_top_k,
                "strategy": "known_issues_and_direct_documents",
                "reranked": self.reranker is not None,
                "retrieved_document_ids": list(dict.fromkeys(item["document_id"] for item in items)),
                "retrieved_chunk_ids": [item["chunk_id"] for item in items],
            },
        )
        return result
