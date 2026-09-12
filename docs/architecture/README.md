# Architecture documentation / 架构文档

This directory explains Echo's evaluation boundary, capability seams, and external-protocol posture.

本目录说明 Echo 的评估边界、能力接缝与外部协议边界。

| File | Responsibility / 职责 |
|---|---|
| [`overview.md`](overview.md) | Evaluation lifecycle, targets, and result flow / 评估生命周期、目标与结果流 |
| [`tool-system.md`](tool-system.md) | Capability ownership and evaluation dispatch / 能力归属与评估分发 |
| [`mcp-integration.md`](mcp-integration.md) | MCP adapter boundary and review checklist / MCP 适配边界与评审清单 |

## Suggested reading order / 推荐阅读顺序

Read `overview.md` first, then `tool-system.md`, and consult `mcp-integration.md` when designing a protocol adapter.

先阅读 `overview.md`，再阅读 `tool-system.md`；设计协议适配器时查阅 `mcp-integration.md`。
