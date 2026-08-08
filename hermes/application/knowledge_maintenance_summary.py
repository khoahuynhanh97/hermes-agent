"""K5 Automated Maintenance Summary.

Reuses K4 maintenance service to produce a concise summary for Hermes.

Does NOT auto-approve, auto-reject, auto-revise, or auto-supersede.
Only detects, flags, summarizes, and proposes.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from hermes.application.knowledge_maintenance import KnowledgeMaintenanceService


@dataclass
class MaintenanceSummary:
    """Summary of K5 maintenance run."""
    owner_user_id: str
    healthy_lessons: int = 0
    needs_reanalysis_count: int = 0
    needs_reanalysis_titles: list[str] = field(default_factory=list)
    open_conflicts_count: int = 0
    open_conflict_reasons: list[str] = field(default_factory=list)
    changed_sources_count: int = 0
    changed_source_ids: list[str] = field(default_factory=list)
    revision_proposals_pending: int = 0
    revision_proposal_titles: list[str] = field(default_factory=list)
    superseded_lessons_count: int = 0
    needs_attention: bool = False
    
    def to_text(self) -> str:
        """Render as concise maintenance summary for Hermes."""
        lines = ["Knowledge Maintenance"]
        lines.append(f"Healthy: {self.healthy_lessons}")
        lines.append(f"Needs reanalysis: {self.needs_reanalysis_count}")
        lines.append(f"Open conflicts: {self.open_conflicts_count}")
        lines.append(f"Changed sources: {self.changed_sources_count}")
        lines.append(f"Revision proposals waiting: {self.revision_proposals_pending}")
        if self.superseded_lessons_count > 0:
            lines.append(f"Superseded lessons (historical): {self.superseded_lessons_count}")
        
        items_needing_attention = []
        for title in self.needs_reanalysis_titles[:5]:
            items_needing_attention.append(f"  - reanalysis: {title}")
        for reason in self.open_conflict_reasons[:5]:
            items_needing_attention.append(f"  - conflict: {reason}")
        for sid in self.changed_source_ids[:5]:
            items_needing_attention.append(f"  - changed source: {sid}")
        for title in self.revision_proposal_titles[:5]:
            items_needing_attention.append(f"  - revision pending: {title}")
        
        if items_needing_attention:
            lines.append("")
            lines.append("Items needing attention:")
            lines.extend(items_needing_attention)
        else:
            lines.append("")
            lines.append("All healthy. No action needed.")
        
        return "\n".join(lines)


class MaintenanceSummaryService:
    """Generates maintenance summary by reading existing state."""
    
    def __init__(self, db_connection_factory, maintenance_service: KnowledgeMaintenanceService | None = None):
        self._db = db_connection_factory
        self._maintenance = maintenance_service or KnowledgeMaintenanceService(db_connection_factory)
    
    def generate_summary(
        self,
        owner_user_id: str,
        source_content_check: dict[str, str] | None = None,
    ) -> MaintenanceSummary:
        """Generate maintenance summary for the owner.
        
        Args:
            owner_user_id: Owner to check
            source_content_check: Optional {source_id: current_content} for
                freshness detection. If None, source freshness is skipped.
        """
        summary = MaintenanceSummary(owner_user_id=owner_user_id)
        
        reanalyzes = self._maintenance.list_needs_reanalysis(owner_user_id)
        summary.needs_reanalysis_count = len(reanalyzes)
        summary.needs_reanalysis_titles = [r["title"] for r in reanalyzes]
        
        conflicts = self._maintenance.list_open_conflicts(owner_user_id)
        summary.open_conflicts_count = len(conflicts)
        summary.open_conflict_reasons = [c.get("reason", "") for c in conflicts]
        
        revisions = self._maintenance.list_revision_proposals(owner_user_id, status="pending")
        summary.revision_proposals_pending = len(revisions)
        summary.revision_proposal_titles = [r.get("proposed_title", "") for r in revisions]
        
        with self._db() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM lessons
                WHERE owner_user_id = ? AND status = 'approved' AND is_current = 1
                """,
                (owner_user_id,),
            ).fetchone()
            summary.healthy_lessons = row["cnt"] if row else 0
            
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM lessons
                WHERE owner_user_id = ? AND is_current = 0
                """,
                (owner_user_id,),
            ).fetchone()
            summary.superseded_lessons_count = row["cnt"] if row else 0
        
        if source_content_check:
            for source_id, new_content in source_content_check.items():
                change = self._maintenance.detect_source_change(owner_user_id, source_id, new_content)
                if change.get("changed") is True:
                    summary.changed_sources_count += 1
                    summary.changed_source_ids.append(source_id)
                    self._flag_dependent_lessons_for_reanalysis(owner_user_id, source_id, change.get("new_hash", ""))
        
        summary.needs_attention = (
            summary.needs_reanalysis_count > 0
            or summary.open_conflicts_count > 0
            or summary.changed_sources_count > 0
            or summary.revision_proposals_pending > 0
        )
        
        return summary
    
    def _flag_dependent_lessons_for_reanalysis(
        self,
        owner_user_id: str,
        source_id: str,
        new_hash: str,
    ) -> None:
        """Flag lessons depending on this source as needs_reanalysis.
        
        Best-effort: lessons can be linked to sources via source_versions or
        via explicit registration. Currently flags all approved lessons of the
        owner that share a source_key with the changed source.
        """
        with self._db() as conn:
            lessons = conn.execute(
                """
                SELECT l.id FROM lessons l
                JOIN sources s ON s.id = l.source_id
                WHERE s.owner_user_id = ? AND s.source_key = ?
                  AND l.status = 'approved'
                """,
                (owner_user_id, source_id),
            ).fetchall()
            
            for lesson_row in lessons:
                self._maintenance.mark_lesson_needs_reanalysis(
                    owner_user_id, lesson_row["id"],
                    reason=f"Source {source_id} changed (new hash {new_hash[:8]})",
                    actor="k5_maintenance",
                )


def create_maintenance_service_for_db(db) -> MaintenanceSummaryService:
    """Helper to create a MaintenanceSummaryService bound to a Database instance."""
    @contextmanager
    def _conn():
        c = db.connect()
        try:
            yield c
        finally:
            c.close()
    
    return MaintenanceSummaryService(_conn)