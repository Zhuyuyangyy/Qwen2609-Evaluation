# RB-AS-002

**Repository:** AgentShield_V3
**Difficulty:** medium

## Task

A session records the TTL it was registered with, and that recorded value is used to decide whether the session is still alive. When a caller supplies an explicit TTL at registration time the recorded metadata and the effective expiry can disagree: the session is treated as having the default lifetime while its recorded TTL says otherwise, so a session expires at the wrong time and the expiry check disagrees with what was recorded. Fix the propagation so the TTL that was actually requested is the one that governs the session. Explicitly passing the default value must remain equivalent to passing nothing.

<details><summary>中文说明</summary>

session 会记录它被注册时使用的 TTL，而该记录值被用于判断 session 是否仍然存活。当调用方在注册时显式提供了 TTL 时，所记录的元数据与实际生效的过期判定可能不一致：session 被按默认生命周期处理，而其记录的 TTL 却显示另一个值，于是 session 在错误的时间过期，过期判定与所记录的内容不符。请修复传播，使实际请求的 TTL 成为真正支配该 session 的值。显式传入默认值必须仍然等价于不传。

</details>

## Constraints

- 不得修改测试
- 不得修改 grader
- 不得改变 public API 签名或默认行为
- 不得改变环境变量默认值的语义
- 不得让显式传入默认值退化为无限或其他值

## How your work is checked

- Test command: `pytest -q`
- Time budget: 1200 seconds
- Public checks are in `public_tests/` and are the ones you can run yourself.
- Additional checks you cannot see are applied after you finish.

Work inside this directory. Do not look for, download, or reproduce the upstream project's history; the repository here is a private snapshot and its history is intentionally absent.
