# Third-party notices / 第三方声明

Echo's first-party source, documentation, schemas, and examples are licensed
under the Apache License 2.0; see [`LICENSE`](LICENSE). No upstream source is
copied into this repository. Runtime and development dependencies remain under
their own licenses and are resolved from [`uv.lock`](uv.lock).

Echo 自有源码、文档、schema 与示例依据 Apache License 2.0 提供，详见 [`LICENSE`](LICENSE)。
本仓库没有复制上游源码。运行时与开发依赖仍适用各自许可证，并由 [`uv.lock`](uv.lock)
解析。

The authoritative direct-dependency, upstream-revision, license, and SBOM
record is [`docs/DEPENDENCY-LICENSES.md`](docs/DEPENDENCY-LICENSES.md). It
records FastAPI, HTTPX, Pydantic, Uvicorn, the Plugins transport/evaluator git
dependencies, and all development tools. The locked transitive graph is not
silently relicensed by Echo's Apache metadata.

权威的直接依赖、上游 revision、许可证与 SBOM 记录位于
[`docs/DEPENDENCY-LICENSES.md`](docs/DEPENDENCY-LICENSES.md)，记录 FastAPI、HTTPX、
Pydantic、Uvicorn、Plugins transport/evaluator git 依赖与全部开发工具。锁定的传递
依赖图不会因 Echo 的 Apache 元数据而被默默重新授权。

Inspect AI is a future replaceable evaluation-engine target, not a current
dependency or execution authority. The Exchange judge remains `WIRED_NOT_RUN`
without a live endpoint and bearer credential; local HTTP doubles are test
fixtures only.

Inspect AI 是未来可替换的评估引擎候选，不是当前依赖或执行权威。没有真实端点与 bearer
凭据时，Exchange 判官仍为 `WIRED_NOT_RUN`；本地 HTTP double 仅用于测试。
