# OWASP Agentic Applications Top 10 (2026) — AgentShield Mapping

This document maps each OWASP Agentic Top 10 risk to AgentShield's mitigation capabilities.

| # | OWASP Risk | AgentShield Mitigation | Status |
|---|-----------|----------------------|--------|
| A1 | Prompt Injection | MCP description injection detection, policy evasion signal | Partial |
| A2 | Sensitive Data Disclosure | Sensitive source detection, output leakage detection, credential access signal | Covered |
| A3 | Supply Chain Vulnerabilities | Tool poisoning detection, rug-pull detection, shadow server detection | Covered |
| A4 | Data Poisoning | Content keyword baseline, LLM-as-Judge baseline | Partial |
| A5 | Unbounded Agency | Three-level governance gate, intervention value analysis | Covered |
| A6 | Broken Authentication | API key auth, OAuth2 stub, mTLS stub | Partial |
| A7 | Insecure Inter-Agent Communication | Cross-agent delegation signal, behavior chain tracking | Covered |
| A8 | Insufficient Authorization | Token scope checking, tenant isolation, consent tracking | Covered |
| A9 | Overreliance on LLM Outputs | Multi-signal risk assessment, graph-derived risk (not LLM-only) | Covered |
| A10 | Lack of Observability | OpenTelemetry integration, append-only audit log, SIEM export | Covered |

### Key Gaps

1. **Prompt Injection (A1)**: AgentShield detects tool-level injection but not direct LLM prompt injection. Integration with input guardrails recommended.
2. **Data Poisoning (A4)**: Requires data validation pipeline upstream of AgentShield.
3. **Authentication (A6)**: OAuth2 and mTLS are stubs; production deployment requires full implementation.
