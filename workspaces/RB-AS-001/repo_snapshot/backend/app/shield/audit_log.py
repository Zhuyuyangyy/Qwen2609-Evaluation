"""AgentShield V3 - Append-Only Audit Log.

Provides tamper-evident audit logging with:
- SHA-256 hash chaining
- Append-only semantics (no deletion or modification)
- Structured evidence export
- OpenTelemetry-compatible span attributes
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class AuditRecord:
    """A single audit record in the append-only log."""
    record_id: str
    event: str
    session_id: str
    tenant_id: str
    data: Dict[str, Any]
    timestamp: float
    previous_hash: str
    record_hash: str
    actor: str = "system"
    decision: str = ""
    risk_score: float = 0.0
    policy_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "event": self.event,
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "data": self.data,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "record_hash": self.record_hash,
            "actor": self.actor,
            "decision": self.decision,
            "risk_score": self.risk_score,
            "policy_id": self.policy_id,
        }


class AppendOnlyAuditLog:
    """Append-only audit log with hash chaining.

    Records cannot be modified or deleted. Each record's hash
    depends on the previous record's hash, making tampering detectable.
    """

    def __init__(self, tenant_id: str = "default"):
        self.tenant_id = tenant_id
        self._records: List[AuditRecord] = []
        self._last_hash = "genesis"

    def append(
        self,
        event: str,
        session_id: str,
        data: Dict[str, Any],
        actor: str = "system",
        decision: str = "",
        risk_score: float = 0.0,
        policy_id: str = "",
    ) -> AuditRecord:
        """Append a new record to the audit log."""
        record_id = f"rec_{uuid.uuid4().hex[:12]}"
        timestamp = time.time()

        # Compute hash
        content = json.dumps({
            "record_id": record_id,
            "event": event,
            "session_id": session_id,
            "tenant_id": self.tenant_id,
            "data": data,
            "timestamp": timestamp,
            "previous_hash": self._last_hash,
            "actor": actor,
            "decision": decision,
            "risk_score": risk_score,
            "policy_id": policy_id,
        }, sort_keys=True, default=str, ensure_ascii=False)
        record_hash = hashlib.sha256(content.encode()).hexdigest()

        record = AuditRecord(
            record_id=record_id,
            event=event,
            session_id=session_id,
            tenant_id=self.tenant_id,
            data=data,
            timestamp=timestamp,
            previous_hash=self._last_hash,
            record_hash=record_hash,
            actor=actor,
            decision=decision,
            risk_score=risk_score,
            policy_id=policy_id,
        )

        self._records.append(record)
        self._last_hash = record_hash
        return record

    def verify_chain(self) -> bool:
        """Verify the integrity of the audit chain.

        Returns True if all hashes are consistent, False if tampering detected.
        """
        expected_prev = "genesis"
        for record in self._records:
            if record.previous_hash != expected_prev:
                return False
            # Recompute hash
            content = json.dumps({
                "record_id": record.record_id,
                "event": record.event,
                "session_id": record.session_id,
                "tenant_id": record.tenant_id,
                "data": record.data,
                "timestamp": record.timestamp,
                "previous_hash": record.previous_hash,
                "actor": record.actor,
                "decision": record.decision,
                "risk_score": record.risk_score,
                "policy_id": record.policy_id,
            }, sort_keys=True, default=str, ensure_ascii=False)
            expected_hash = hashlib.sha256(content.encode()).hexdigest()
            if record.record_hash != expected_hash:
                return False
            expected_prev = record.record_hash
        return True

    def export_records(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Export audit records as a list of dicts."""
        records = self._records[-limit:] if limit else self._records
        return [r.to_dict() for r in records]

    def query(
        self,
        session_id: Optional[str] = None,
        event: Optional[str] = None,
        decision: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> List[AuditRecord]:
        """Query audit records with filters."""
        results = []
        for record in self._records:
            if session_id and record.session_id != session_id:
                continue
            if event and record.event != event:
                continue
            if decision and record.decision != decision:
                continue
            if start_time and record.timestamp < start_time:
                continue
            if end_time and record.timestamp > end_time:
                continue
            results.append(record)
        return results

    @property
    def record_count(self) -> int:
        return len(self._records)

    @property
    def last_hash(self) -> str:
        return self._last_hash
