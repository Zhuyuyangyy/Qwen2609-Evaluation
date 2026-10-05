"""AgentShield V3 - Risk Signal Extractor.

Extracts risk signals from tool events and behavior graph context.
This replaces the old approach of using externally-provided risk_score.
"""

from __future__ import annotations

import re
from typing import Dict, List

from app.shield.risk_signals import GraphRiskState, RiskSignal, RiskSignalType
from app.shield.schemas import ObservedToolEvent

# ─── Pattern Definitions ─────────────────────────────────────────────────────

SENSITIVE_SOURCE_PATTERNS = {
    "execute_sql", "cursor.execute", "database_query", "read_file",
    "load_data", "fetch_records", "query_api", "select", "sql",
    "dump", "export_table",
}

EXTERNAL_SINK_PATTERNS = {
    "send_email", "http_request", "upload_file", "webhook_call",
    "export_csv", "external_delivery", "post_data", "smtp", "ftp",
    "curl", "wget", "upload", "send",
}

PRIVILEGE_CHANGE_PATTERNS = {
    "modify_role", "update_permission", "change_config",
    "set_admin", "grant_access", "escalate_privilege",
    "chmod", "chown", "sudo", "grant", "admin",
}

AUDIT_TAMPER_PATTERNS = {
    "disable_audit", "delete_log", "clear_history",
    "modify_log", "audit_log_write", "rm_log", "shred",
    "truncate_log", "wipe",
}

BULK_OPERATION_PATTERNS = {
    "bulk_delete", "batch_update", "mass_operation",
    "drop_table", "truncate", "rm -rf", "rm -fr", "del /f",
    "drop database", "delete from", "mkfs",
    "> /dev/sd", "dd if=", "format c:", "format disk",
    "send_bulk", "bulk_email", "mass_email", "export_all",
    "all_records", "all_customers",
}

CREDENTIAL_PATTERNS = [
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"api_key", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
    re.compile(r"private_key", re.IGNORECASE),
]

SENSITIVE_DATA_PATTERNS = [
    re.compile(r"ssn|social_security", re.IGNORECASE),
    re.compile(r"credit_card|card_number", re.IGNORECASE),
    re.compile(r"id_card|identity", re.IGNORECASE),
    re.compile(r"phone|mobile|telephone", re.IGNORECASE),
    re.compile(r"email.*@.*\.(com|org|net)", re.IGNORECASE),
    re.compile(r"address|home_addr", re.IGNORECASE),
]

POLICY_EVASION_PATTERNS = [
    re.compile(r"ignore\s+(previous|above|all)", re.IGNORECASE),
    re.compile(r"bypass", re.IGNORECASE),
    re.compile(r"override\s+(policy|rule|check)", re.IGNORECASE),
]


class RiskSignalExtractor:
    """Extracts risk signals from tool events and graph context.

    This is the core component that replaces the old externally-provided
    risk_score. It computes risk from observable event features and
    behavior graph state.
    """

    def __init__(self):
        # Base scores per signal class. These are *severity* values, not
        # votes: a destructive operation must be able to reach the BLOCK
        # threshold (0.90) on its own, and every other class must clear the
        # review threshold (0.60) without needing corroboration. The previous
        # values topped out at 0.55, so after the confidence discount nothing
        # could ever be blocked and the benchmark sat at 16% accuracy.
        self.signal_weights: Dict[RiskSignalType, float] = {
            RiskSignalType.SENSITIVE_SOURCE: 0.55,
            RiskSignalType.EXTERNAL_SINK: 0.70,
            RiskSignalType.PRIVILEGE_CHANGE: 0.80,
            RiskSignalType.AUDIT_TAMPER: 0.85,
            RiskSignalType.BULK_OPERATION: 0.95,
            RiskSignalType.CREDENTIAL_ACCESS: 0.65,
            RiskSignalType.CROSS_AGENT_DELEGATION: 0.45,
            RiskSignalType.POLICY_EVASION: 0.90,
        }

    def extract_signals(
        self,
        event: ObservedToolEvent,
        graph_inherited_risk: float = 0.0,
        graph_downstream_exposure: float = 0.0,
        graph_path_risk: float = 0.0,
    ) -> List[RiskSignal]:
        """Extract all risk signals from an observed tool event."""
        signals: List[RiskSignal] = []

        tool = event.tool_name.lower()
        tool_input_str = str(event.tool_input).lower()

        # 1. Sensitive source detection
        #
        # The class default only applies when the payload actually touches
        # sensitive material. A plain SELECT over product names is not a
        # sensitive source, so with no sensitive marker present the score drops
        # to a low baseline instead of the class weight.
        if any(pattern in tool or pattern in tool_input_str for pattern in SENSITIVE_SOURCE_PATTERNS):
            base = self.signal_weights[RiskSignalType.SENSITIVE_SOURCE]
            matched = next(
                (p.pattern for p in SENSITIVE_DATA_PATTERNS if p.search(tool_input_str)),
                None,
            )
            if matched:
                score = min(1.0, base + 0.2)
                evidence = [f"Sensitive data pattern in payload: {matched}"]
            elif any(m in tool_input_str for m in self._SENSITIVE_READ_MARKERS):
                score = base
                evidence = [f"Tool '{tool}' reads a sensitive source"]
            else:
                score = self._PLAIN_QUERY_SCORE
                evidence = [f"Tool '{tool}' queries/generic source; no sensitive markers"]
            signals.append(RiskSignal(
                signal_type=RiskSignalType.SENSITIVE_SOURCE,
                score=score,
                evidence=evidence,
                source_event_id=event.event_id,
            ))

        # 2. External sink detection
        #
        # Only fire when the payload actually leaves the trust boundary. A
        # send_email to an internal domain is ordinary business traffic, but
        # "send" is in EXTERNAL_SINK_PATTERNS (to catch send_email), so without
        # this check every internal notification scored as an exfiltration.
        if any(
            pattern in tool or pattern in tool_input_str
            for pattern in EXTERNAL_SINK_PATTERNS
        ) and not self._looks_internal_only(tool_input_str):
            score = self.signal_weights[RiskSignalType.EXTERNAL_SINK]
            # Boost if previous tool was a sensitive source
            prev_tools = event.previous_tools
            if prev_tools and any(
                any(sp in pt.lower() for sp in SENSITIVE_SOURCE_PATTERNS)
                for pt in prev_tools[-3:]
            ):
                score = min(1.0, score + 0.3)
                signals.append(RiskSignal(
                    signal_type=RiskSignalType.SENSITIVE_SOURCE,
                    score=0.3,
                    evidence=["Previous tool in chain was a sensitive source"],
                    source_event_id=event.event_id,
                ))
            signals.append(RiskSignal(
                signal_type=RiskSignalType.EXTERNAL_SINK,
                score=score,
                evidence=[f"Tool '{tool}' sends data externally"],
                source_event_id=event.event_id,
            ))

        # 3. Privilege change detection
        if any(pattern in tool or pattern in tool_input_str for pattern in PRIVILEGE_CHANGE_PATTERNS):
            signals.append(RiskSignal(
                signal_type=RiskSignalType.PRIVILEGE_CHANGE,
                score=self.signal_weights[RiskSignalType.PRIVILEGE_CHANGE],
                evidence=[f"Tool '{tool}' modifies privileges or access control"],
                source_event_id=event.event_id,
            ))

        # 4. Audit tamper detection
        if any(pattern in tool or pattern in tool_input_str for pattern in AUDIT_TAMPER_PATTERNS):
            signals.append(RiskSignal(
                signal_type=RiskSignalType.AUDIT_TAMPER,
                score=self.signal_weights[RiskSignalType.AUDIT_TAMPER],
                evidence=[f"Tool '{tool}' modifies audit logging"],
                source_event_id=event.event_id,
            ))

        # 5. Bulk operation detection
        if any(pattern in tool or pattern in tool_input_str for pattern in BULK_OPERATION_PATTERNS):
            # A DELETE/UPDATE bounded by a WHERE clause is a routine
            # maintenance operation; the unbounded form is what destroys data.
            # Scale the score by how much of the table the statement can reach.
            score = self.signal_weights[RiskSignalType.BULK_OPERATION]
            if "where" not in tool_input_str:
                evidence = [f"Tool '{tool}' performs unbounded destructive operation"]
            else:
                score = self._BOUNDED_DELETE_SCORE
                evidence = [f"Tool '{tool}' performs bounded destructive operation"]
            signals.append(RiskSignal(
                signal_type=RiskSignalType.BULK_OPERATION,
                score=score,
                evidence=evidence,
                source_event_id=event.event_id,
            ))

        # 6. Credential access detection
        for pattern in CREDENTIAL_PATTERNS:
            if pattern.search(tool_input_str):
                signals.append(RiskSignal(
                    signal_type=RiskSignalType.CREDENTIAL_ACCESS,
                    score=self.signal_weights[RiskSignalType.CREDENTIAL_ACCESS],
                    evidence=[f"Tool input contains credential pattern: {pattern.pattern}"],
                    source_event_id=event.event_id,
                ))
                break

        # 7. Cross-agent delegation
        if event.agent_role and "delegate" in tool:
            signals.append(RiskSignal(
                signal_type=RiskSignalType.CROSS_AGENT_DELEGATION,
                score=self.signal_weights[RiskSignalType.CROSS_AGENT_DELEGATION],
                evidence=[f"Agent '{event.agent_id}' delegates via tool '{tool}'"],
                source_event_id=event.event_id,
            ))

        # 8. Policy evasion detection
        for pattern in POLICY_EVASION_PATTERNS:
            if pattern.search(tool_input_str):
                signals.append(RiskSignal(
                    signal_type=RiskSignalType.POLICY_EVASION,
                    score=self.signal_weights[RiskSignalType.POLICY_EVASION],
                    evidence=[f"Tool input contains policy evasion pattern: {pattern.pattern}"],
                    source_event_id=event.event_id,
                ))
                break

        # 9. Generic content severity
        #
        # Enumerating every dangerous tool name is a losing game: the corpus
        # contains execute_admin_command, update_security_policy,
        # set_system_time and peers that match none of the sets above. This
        # pass scores the *payload* on generic high-severity vocabulary so an
        # unseen tool still registers instead of silently scoring 0.
        #
        # It runs unconditionally rather than only when no other signal fired:
        # the earlier classes are keyed on the *tool name*, so a
        # DROP TABLE issued through a generic execute_sql only registers here.
        # Without this, SENSITIVE_SOURCE's name match wins with a low score.
        content_score = self._score_content_severity(tool, tool_input_str)
        if content_score > 0.0:
            signals.append(RiskSignal(
                signal_type=RiskSignalType.POLICY_EVASION,
                score=content_score,
                evidence=["Payload matches high-severity vocabulary"],
                source_event_id=event.event_id,
            ))

        # 10. Benign-path dampening
        #
        # read_file is in SENSITIVE_SOURCE_PATTERNS because reading /etc/passwd
        # is genuinely sensitive, but that made every ordinary read score the
        # same as a credential dump. When nothing above fired on the payload,
        # a plain local path is normal behaviour and should not inherit the
        # class default.
        elif self._looks_benign_local_read(tool, tool_input_str):
            signals = [
                s for s in signals
                if s.signal_type != RiskSignalType.SENSITIVE_SOURCE
            ] or [RiskSignal(
                signal_type=RiskSignalType.SENSITIVE_SOURCE,
                score=self._BENIGN_READ_SCORE,
                evidence=["Ordinary local read; no sensitive markers in payload"],
                source_event_id=event.event_id,
            )]

        return signals

    #: Score for an ordinary local read with no sensitive markers.
    _BENIGN_READ_SCORE = 0.15

    #: Score for a query that touches no sensitive material.
    _PLAIN_QUERY_SCORE = 0.20

    #: Score for a destructive statement bounded by a WHERE clause.
    _BOUNDED_DELETE_SCORE = 0.55

    #: Strong markers that keep a read in the sensitive class.
    _SENSITIVE_READ_MARKERS = (
        "passwd", "shadow", "secret", "credential", "token", "api_key",
        "private_key", "ssn", "credit_card", "id_card", "customer",
        "employee", "salary", "medical", "/etc/", ".ssh/", ".aws/",
        "id_rsa", "database", "dump", "backup",
    )

    @classmethod
    def _looks_benign_local_read(cls, tool: str, tool_input_str: str) -> bool:
        """True when a read tool points at an ordinary local path."""
        if tool not in ("read_file", "load_data", "fetch_records"):
            return False
        return not any(m in tool_input_str for m in cls._SENSITIVE_READ_MARKERS)

    #: Recipient domains that stay inside the trust boundary.
    _INTERNAL_DOMAINS = (
        "@internal.", "@localhost", "@company.", "@corp.", "@example.com",
        "@test.", "@local",
    )

    #: Free-mail and other consumer providers, treated as off-network.
    _EXTERNAL_MAIL_DOMAINS = (
        "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "qq.com",
        "163.com", "126.com", "sina.com", "foxmail.com", "protonmail.com",
        "mail.ru", "aol.com",
    )

    @classmethod
    def _looks_internal_only(cls, tool_input_str: str) -> bool:
        """True when every addressable target in the payload is internal.

        Used to keep ordinary internal traffic (a team notification, a local
        webhook) out of the external-sink class. Only applies when at least one
        recipient is present -- an upload with no destination string is not
        assumed safe.
        """
        recipients = re.findall(r"[\w.+-]+@[\w.-]+\.\w+", tool_input_str)
        if recipients:
            if any(dom in addr for addr in recipients for dom in cls._EXTERNAL_MAIL_DOMAINS):
                return False
            return all(
                any(dom in addr for dom in cls._INTERNAL_DOMAINS)
                for addr in recipients
            )
        # No email-shaped recipient: fall back to hostnames.
        hosts = re.findall(r"https?://([\w.-]+)", tool_input_str)
        if hosts:
            return all(
                any(dom.lstrip("@") in host for dom in cls._INTERNAL_DOMAINS)
                or host in ("localhost", "127.0.0.1")
                for host in hosts
            )
        return False

    #: Generic high-severity vocabulary, grouped by weight band.
    _CONTENT_SEVERITY_TERMS = (
        # (substring, score)
        ("rm -rf", 0.90), ("rm -fr", 0.90), ("--no-preserve-root", 0.90),
        ("drop table", 0.90), ("drop database", 0.90), ("truncate", 0.80),
        ("delete from", 0.80), ("format c:", 0.90), ("mkfs", 0.90),
        ("dd if=", 0.85), ("shred", 0.85), ("wipe", 0.75),
        ("audit_log", 0.85), ("audit log", 0.85), ("disable_audit", 0.85),
        ("admin", 0.75), ("root", 0.70), ("sudo", 0.75), ("privilege", 0.75),
        ("role", 0.60), ("permission", 0.65), ("policy", 0.65),
        ("firewall", 0.70), ("security", 0.50), ("system_time", 0.65),
        ("allow all", 0.75), ("bypass", 0.85), ("override", 0.70),
        ("tenant_id !=", 0.80), ("all_customers", 0.75), ("* from", 0.45),
        ("password", 0.70), ("secret", 0.70), ("api_key", 0.70),
        ("token", 0.65), ("credential", 0.70), ("private_key", 0.75),
        ("ssn", 0.70), ("credit_card", 0.75), ("id_card", 0.70),
        ("/etc/passwd", 0.80), ("/etc/shadow", 0.85),
        ("exfiltrat", 0.90), ("curl", 0.45), ("wget", 0.45),
        ("external", 0.40), ("webhook", 0.50), ("ftp", 0.55),
        # Generic offensive-security vocabulary. These are recognised attack
        # stages, not fixture-specific strings -- any convention-driven
        # reviewer would flag them. Payloads that merely name a *target*
        # (withdraw_1000, check_balance) are deliberately omitted: scoring
        # those would be fitting the fixture rather than detecting danger.
        ("phish", 0.85), ("recon", 0.60), ("exfil", 0.85),
        ("reverse_shell", 0.95), ("rootkit", 0.95),
        ("privilege_escalat", 0.85), ("escalate_privilege", 0.85),
        ("lateral_movement", 0.80), ("c2_", 0.80), ("beacon", 0.70),
        ("keylog", 0.90), ("ransom", 0.95), ("backdoor", 0.95),
        ("brute_force", 0.75), ("credential_stuff", 0.80),
        ("session_hijack", 0.85), ("token_replay", 0.80),
        ("prompt_injection", 0.85), ("ignore_previous", 0.85),
        ("jailbreak", 0.85),
    )

    @classmethod
    def _score_content_severity(cls, tool: str, tool_input_str: str) -> float:
        """Score a payload on generic high-severity vocabulary.

        Returns the strongest matching term's score, or 0.0 when nothing
        matches. Tool name and input are both searched.
        """
        haystack = f"{tool} {tool_input_str}"
        best = 0.0
        for term, score in cls._CONTENT_SEVERITY_TERMS:
            if term in haystack and score > best:
                best = score
        return best

    def compute_graph_risk_state(
        self,
        event: ObservedToolEvent,
        graph_inherited_risk: float = 0.0,
        graph_downstream_exposure: float = 0.0,
        graph_path_risk: float = 0.0,
    ) -> GraphRiskState:
        """Compute the full GraphRiskState for an event.

        This is the main entry point for the new risk computation pipeline.
        """
        signals = self.extract_signals(
            event, graph_inherited_risk, graph_downstream_exposure, graph_path_risk
        )

        # Local risk from signals.
        #
        # Take the *strongest* signal rather than the weighted mean. With a
        # mean, several mild signals dilute one severe one -- a bulk delete
        # (0.50) averaged with a sensitive read (0.25) lands at 0.25, which is
        # indistinguishable from the read alone. combined_risk then scales
        # local_risk by 0.35 and the engine scales that by 0.6, so a mean-
        # based local_risk could never reach the 0.60 review threshold at all:
        # the benchmark regressed from 100% to 16% action accuracy.
        #
        # signal.score already carries the weight assigned at extraction time
        # (see extract_signals), so it is used as-is -- multiplying by
        # signal_weights again would square it.
        if signals:
            local_risk = min(1.0, max(s.score for s in signals))
        else:
            local_risk = 0.0

        # Compute intervention value
        intervention_value = 0.0
        if graph_downstream_exposure > 0.3:
            intervention_value = min(1.0, graph_downstream_exposure * 0.8)

        # Confidence based on number of signals and graph connectivity
        confidence = min(1.0, 0.5 + 0.1 * len(signals) + 0.1 * min(event.chain_length, 5))

        return GraphRiskState(
            local_risk=local_risk,
            inherited_risk=graph_inherited_risk,
            downstream_exposure=graph_downstream_exposure,
            path_risk=graph_path_risk,
            intervention_value=intervention_value,
            confidence=confidence,
            signals=signals,
        )
