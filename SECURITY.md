# Security policy / 安全政策

## Reporting a vulnerability / 报告漏洞

Please do not open a public issue for an unpatched vulnerability. Use GitHub
private vulnerability reporting when it is enabled for this repository. If that
channel is unavailable, contact the DoHorizon-AI repository maintainers through
the organisation's private security channel. Include only a minimal
reproduction, affected revision or component, deployment assumptions, and the
expected security boundary. Do not include credentials, tokens, tenant data,
model outputs, or private endpoint details.

请勿在公开 issue 中披露尚未修复的漏洞。仓库启用 GitHub 私密漏洞报告后，请
优先使用该渠道；如果该渠道不可用，请通过 DoHorizon-AI 组织的私密安全渠道联系
维护者。仅提供最小复现、受影响的版本或组件、部署前提与预期安全边界，不要包含
凭据、令牌、租户数据、模型输出或私有端点详情。

## Security boundary / 安全边界

Echo owns evaluation state, result evidence, gate decisions, annotations, and
explicit feedback selection. Catalyst owns dataset state, Yield owns training,
Reactor owns serving, and Platform owns generic lifecycle, identity, lease,
fence, and Artifact Plane mechanisms. Echo consumes those Products through
explicit Product APIs and opaque `ArtifactRef` or `connection_ref` values; it
does not provide a tenant-isolation or process-sandbox boundary.

Echo 负责评估状态、结果证据、门禁决策、标注与显式反馈选择。Catalyst 负责数据集状态，
Yield 负责训练，Reactor 负责服务，Platform 负责通用生命周期、身份、租约、围栏与制品
平面机制。Echo 通过显式产品 API 以及透明的 `ArtifactRef` 或 `connection_ref` 消费这些
能力；Echo 不提供租户隔离或进程沙箱边界。

## Important non-guarantees / 重要限制

- A passing deterministic evaluator test is not proof of live judge correctness,
  arbitrary endpoint safety, tenant isolation, or production authorization.
- `WIRED_NOT_RUN` means the adapter is intentionally fail-closed without a
  reachable endpoint and credential; it is not live acceptance.
- Test doubles, local Artifact Plane storage, and example JSONL are not
  production data-handling or authentication evidence.
- Publishing the source does not publish credentials, tenant data, model
  outputs, datasets, or private infrastructure.

- 确定性评估器测试通过，不代表真实判官正确、任意端点安全、租户隔离或生产授权已经验收。
- `WIRED_NOT_RUN` 表示缺少可达端点与凭据时适配器会有意 fail closed，并不表示真实验收通过。
- 测试替身、本地制品平面与示例 JSONL 不构成生产数据处理或认证证据。
- 公开源码不会公开凭据、租户数据、模型输出、数据集或私有基础设施。
