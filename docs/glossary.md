# Glossary / 术语表

| English | 中文 | Meaning / 含义 |
|---|---|---|
| Echo | Echo 评估服务 | Cyrene Product for model and session evaluation, gates, and feedback / Cyrene 的模型与会话评估、门禁与反馈产品 |
| EvaluationSuite | 评估套件 | Named evaluator, expected/actual fields, and threshold policy / 由评估器、期望/实际字段与阈值策略组成的命名集合 |
| EvaluationRun | 评估运行 | One bound execution of a selected runner against an input artifact / 选定运行器对输入制品的一次绑定执行 |
| EvaluationResult | 评估结果 | Immutable score, counts, and report reference for a run / 某次运行的不可变分数、计数与报告引用 |
| GateDecision | 门禁决策 | `PASS`/`FAIL` policy outcome for a run / 运行对应的 `PASS`/`FAIL` 策略结果 |
| SampleRecord | 逐样本记录 | Immutable per-sample evidence anchored to one run / 锚定到某次运行的不可变逐样本证据 |
| HumanAnnotation | 人工标注 | Human review record; never mutates model measurements / 人工评审记录；不改写模型测量 |
| FeedbackSet | 反馈集 | Selected training candidates; `OPEN -> EXPORTED` / 选定的训练候选；`OPEN -> EXPORTED` |
| HandoffReceipt | 交接回执 | Target-confirmed acknowledgement of a direct Product handoff / 直连产品交接的目标确认回执 |
| Runner profile | 运行器配置档 | Echo-local profile: `DIRECT_PLUGIN` or `PRODUCT_ADAPTER` / Echo 本地配置档：`DIRECT_PLUGIN` 或 `PRODUCT_ADAPTER` |
| Runner binding | 运行器绑定 | Declared `engineBindingId` mapped to one profile and evaluator / 已声明 `engineBindingId` 到配置档与评估器的映射 |
| Acceptance class | 验收分级 | `LOCAL_ENDPOINT_VERIFIED`, `WIRED_NOT_RUN`, or `MOCK` (test doubles only) / `LOCAL_ENDPOINT_VERIFIED`、`WIRED_NOT_RUN`，或仅测试替身使用的 `MOCK` |
| Evaluation target | 评估目标 | The served model output captured in an input artifact / 记录在输入制品中的被评估模型输出 |
| ModelVersion | 模型版本 | Versioned model identity, commonly produced by Yield / 带版本模型身份，通常由 Yield 产出 |
| LLM judge | LLM 评审器 | Model-assisted scorer invoked through the Exchange endpoint / 通过 Exchange 端点调用的模型评审器 |
| Capability seam | 能力接缝 | Versioned interface used to consume an external capability / 消费外部能力的带版本接口 |
| ArtifactRef | 制品引用 | Provider-neutral immutable content identity / 与提供方无关的不可变内容身份 |
| WIRED_NOT_RUN | 已接线未运行 | Wired but without live acceptance evidence / 已接线但尚无真实验收证据 |
| NOT_DEFINED | 未定义 | Capability that Echo does not define or assume / Echo 不定义也不假设的能力 |
