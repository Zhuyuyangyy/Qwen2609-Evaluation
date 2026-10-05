# MCP Security Best Practices — AgentShield Mapping

Maps MCP official security recommendations to AgentShield capabilities.

| MCP Security Concern | AgentShield Mitigation |
|---------------------|----------------------|
| Confused Deputy | Cross-agent delegation signal, consent tracking |
| Token Passthrough | Token scope checking, auth_scope validation |
| SSRF | External sink detection, URL pattern analysis |
| Session Hijacking | Session-scoped proxy, tenant isolation |
| Local MCP Server Compromise | Tool poisoning detection, rug-pull detection |
| Scope Minimization | Token scope enforcement, per-tool rate limits |
| Tool Description Manipulation | Rug-pull detection (hash comparison), description injection scanning |
| Shadow Server Injection | Shadow server detection at registration and call time |
| Data Exfiltration via Tools | Sensitive source → external sink chain detection, output leakage detection |
| Cascading Attacks | Cascade depth analysis, amplification factor computation |
