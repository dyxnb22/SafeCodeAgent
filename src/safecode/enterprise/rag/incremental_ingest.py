"""Incremental knowledge ingest with freshness and ACL sync (v2.4.2)."""

from __future__ import annotations

from dataclasses import dataclass, field

from safecode.enterprise.rag.exceptions import AclSyncError
from safecode.enterprise.rag.models import Chunk, Freshness
from safecode.enterprise.rag.vector_store import KnowledgeVectorStore


@dataclass
class IngestReport:
    source_id: str
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    acl_updated: int = 0
    freshness_updated: int = 0


@dataclass
class IncrementalIngestor:
    store: KnowledgeVectorStore
    fail_closed_on_acl_sync: bool = True
    _acl_failures: list[str] = field(default_factory=list)

    def ingest_source(
        self,
        tenant_id: str,
        source_id: str,
        chunks: list[Chunk],
        *,
        freshness: Freshness = "current",
    ) -> IngestReport:
        existing = {
            chunk.chunk_id: chunk
            for chunk in self.store.list_chunks(tenant_id)
            if chunk.source_id == source_id
        }
        to_write: list[Chunk] = []
        report = IngestReport(source_id=source_id)
        incoming_ids = {chunk.chunk_id for chunk in chunks}

        for chunk in chunks:
            normalized = chunk.model_copy(update={"tenant_id": tenant_id, "freshness": freshness})
            prior = existing.get(chunk.chunk_id)
            if prior is None:
                to_write.append(normalized)
                report.inserted += 1
                continue
            if prior.hash == chunk.hash and prior.text == chunk.text:
                if prior.permission_scope != chunk.permission_scope:
                    if not self._sync_acl(tenant_id, chunk):
                        if self.fail_closed_on_acl_sync:
                            raise AclSyncError(
                                f"ACL sync failed for chunk {chunk.chunk_id} in source {source_id}"
                            )
                        report.skipped += 1
                        continue
                    report.acl_updated += 1
                if prior.freshness != freshness:
                    self.store.update_freshness(tenant_id, [chunk.chunk_id], freshness)
                    report.freshness_updated += 1
                report.skipped += 1
                continue
            to_write.append(normalized)
            report.updated += 1

        if to_write:
            self.store.upsert_chunks(tenant_id, to_write)

        stale_ids = [
            chunk_id for chunk_id, chunk in existing.items() if chunk_id not in incoming_ids
        ]
        if stale_ids:
            self.store.update_freshness(tenant_id, stale_ids, "superseded")
            report.freshness_updated += len(stale_ids)

        return report

    def _sync_acl(self, tenant_id: str, chunk: Chunk) -> bool:
        try:
            self.store.update_permission_scope(tenant_id, chunk.chunk_id, chunk.permission_scope)
            return True
        except Exception:
            self._acl_failures.append(chunk.chunk_id)
            return False
