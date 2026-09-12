"""
┌─────────────────────────────────────────────────────────────────────┐
│  📄 ui_page.py                                                      │
│  Module: cyrene_echo.ui_page                                        │
│  Role: Minimal sample-list / compare / score / filter / export page. │
│                                                                     │
│  模块职责：提供样本列表、对比、评分、筛选与导出的最小界面（非基准平台）。 │
└─────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>Echo · 会话评估与反馈</title>
<style>
  :root { color-scheme: light dark; }
  body { font: 14px/1.45 system-ui, "Segoe UI", "Noto Sans CJK SC", sans-serif; margin: 0; display: flex; }
  nav { width: 220px; padding: 16px; border-right: 1px solid #8884; }
  main { padding: 16px; flex: 1; }
  h1 { font-size: 16px; margin: 0 0 12px; }
  h2 { font-size: 14px; margin: 18px 0 8px; }
  section { display: none; }
  section.active { display: block; }
  label { display: block; margin: 6px 0 2px; font-size: 12px; opacity: .85; }
  input, textarea, select, button { box-sizing: border-box; width: 100%; padding: 6px; font: inherit; }
  button { cursor: pointer; margin-top: 8px; }
  .row { display: flex; gap: 8px; }
  .row > * { flex: 1; }
  table { width: 100%; border-collapse: collapse; margin-top: 8px; }
  th, td { border: 1px solid #8884; padding: 6px; text-align: left; vertical-align: top; font-size: 12px; }
  th { background: #8884; }
  .pass { color: #2a8; font-weight: 600; }
  .fail { color: #c33; font-weight: 600; }
  .badge { display: inline-block; padding: 1px 6px; border-radius: 3px; background: #3385ff; color: #fff; font-size: 11px; margin-left: 6px; }
  pre { background: #8884; padding: 8px; overflow: auto; max-height: 260px; white-space: pre-wrap; }
  a { color: #3385ff; }
</style>
</head>
<body>
<nav>
  <h1>Echo Feedback</h1>
  <button data-nav="import">1 · 导入会话</button><p>
  <button data-nav="suite">2 · 评估方式</button><p>
  <button data-nav="run">3 · 执行评估</button><p>
  <button data-nav="samples">4 · 样本与评分</button><p>
  <button data-nav="export">5 · 导出反馈集</button>
</nav>
<main>
  <section id="import" class="active">
    <h2>导入会话/模型输出</h2>
    <p>粘贴 JSONL：每行一条样本，建议字段 <code>instruction / expected / actual / output / model / endpoint</code>。</p>
    <textarea id="import-body" rows="8">{"instruction":"2+2?","expected":"4","actual":"4","output":"4","model":"qwen-demo","endpoint":"http://reactor/v1"}
{"instruction":"首都?","expected":"北京","actual":"上海","output":"上海","model":"qwen-demo","endpoint":"http://reactor/v1"}
{"instruction":"水分子式?","expected":"H2O","actual":"H2O","output":"H2O","model":"qwen-demo","endpoint":"http://reactor/v1"}
</textarea>
    <button id="import-btn">发布为 ArtifactRef</button>
    <pre id="import-out"></pre>
  </section>

  <section id="suite">
    <h2>评估方式（EvaluationSuite）</h2>
    <label>名称</label><input id="suite-name" value="demo-exact" />
    <label>评估器</label>
    <select id="suite-evaluator"><option value="exact_match.v1">exact_match.v1（确定性）</option><option value="llm_judge.v1">llm_judge.v1（经 Exchange）</option></select>
    <label>期望字段</label><input id="suite-expected" value="expected" />
    <label>实际字段</label><input id="suite-actual" value="actual" />
    <label>门禁阈值（0-1）</label><input id="suite-threshold" value="0.7" />
    <label>Judge Profile ID（仅 llm_judge）</label><input id="suite-judge" placeholder="可选" />
    <button id="suite-btn">创建评估套件</button>
    <pre id="suite-out"></pre>
  </section>

  <section id="run">
    <h2>执行评估</h2>
    <label>Suite ID</label><input id="run-suite" />
    <label>输入 ArtifactRef JSON</label><textarea id="run-artifact" rows="4"></textarea>
    <label>引擎绑定</label><input id="run-binding" value="exact-match-plugin" />
    <button id="run-btn">执行 EvaluationRun</button>
    <pre id="run-out"></pre>
  </section>

  <section id="samples">
    <h2>样本列表 / 筛选 / 人工评分</h2>
    <label>Run ID</label><input id="samples-run" />
    <div class="row">
      <div><label>仅未通过</label><input id="filter-failed" type="checkbox" /></div>
      <div><label>仅已标注</label><input id="filter-annotated" type="checkbox" /></div>
    </div>
    <button id="samples-btn">加载样本</button>
    <table id="samples-table">
      <thead><tr><th>#</th><th>期望/实际</th><th>结果</th><th>usage</th><th>人工评分</th><th>标注</th></tr></thead>
      <tbody></tbody>
    </table>
  </section>

  <section id="export">
    <h2>反馈集 / 训练候选导出</h2>
    <label>Run ID</label><input id="export-run" />
    <label>名称</label><input id="export-name" value="demo-feedback" />
    <label>选中的样本序号（逗号分隔，必须由用户显式选择）</label>
    <input id="export-indexes" value="1,2" />
    <button id="export-btn">创建 FeedbackSet</button>
    <pre id="export-out"></pre>
    <div id="export-actions" hidden>
      <a id="export-download" href="#">下载 Catalyst 兼容 JSONL</a>
    </div>
  </section>
</main>

<script>
const $ = (id) => document.getElementById(id);
const json = (r) => r.headers.get("content-type")?.includes("problem") ? r.json() : r.json();

function show(id) {
  document.querySelectorAll("section").forEach((s) => s.classList.remove("active"));
  $(id).classList.add("active");
}
document.querySelectorAll("[data-nav]").forEach((b) =>
  b.addEventListener("click", () => show(b.dataset.nav))
);

function lastId(pre, obj) {
  $(pre).textContent = JSON.stringify(obj, null, 2);
  return obj.id;
}

$("import-btn").addEventListener("click", async () => {
  const body = $("import-body").value;
  const res = await fetch("/api/v1/session-artifacts", { method: "POST", body, headers: { "Content-Type": "application/jsonl" } });
  const obj = await json(res);
  $("import-out").textContent = JSON.stringify(obj, null, 2);
  $("run-artifact").value = JSON.stringify(obj, null, 2);
});

$("suite-btn").addEventListener("click", async () => {
  const evaluator = $("suite-evaluator").value;
  const body = {
    name: $("suite-name").value,
    evaluator,
    expectedField: $("suite-expected").value,
    actualField: $("suite-actual").value,
    threshold: Number($("suite-threshold").value),
  };
  const jid = $("suite-judge").value.trim();
  if (jid) body.judgeProfileId = jid;
  const res = await fetch("/api/v1/evaluation-suites", { method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "application/json" } });
  const obj = await json(res);
  lastId("suite-out", obj);
  $("run-suite").value = obj.id;
});

$("run-btn").addEventListener("click", async () => {
  const body = {
    suiteId: $("run-suite").value,
    inputArtifact: JSON.parse($("run-artifact").value),
    engineBindingId: $("run-binding").value,
  };
  const res = await fetch("/api/v1/evaluation-runs", { method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "application/json" } });
  const obj = await json(res);
  $("run-out").textContent = JSON.stringify(obj, null, 2);
  $("samples-run").value = obj.id;
  $("export-run").value = obj.id;
});

$("samples-btn").addEventListener("click", async () => {
  const runId = $("samples-run").value;
  const params = new URLSearchParams();
  if ($("filter-failed").checked) params.set("only_passed", "false");
  if ($("filter-annotated").checked) params.set("only_annotated", "true");
  const res = await fetch(`/api/v1/evaluation-runs/${runId}/samples?${params}`);
  const samples = await json(res);
  const annotations = await (await fetch(`/api/v1/evaluation-runs/${runId}/annotations`)).json();
  const annByIndex = new Map(annotations.map((a) => [a.sampleIndex, a]));
  const tbody = $("#samples-table tbody");
  tbody.innerHTML = "";
  for (const s of samples) {
    const tr = document.createElement("tr");
    const cls = s.passed ? "pass" : "fail";
    const usage = s.usage ? `${s.usage.promptTokens ?? "?"}/${s.usage.completionTokens ?? "?"}/${s.usage.totalTokens ?? "?"}` : "<i>未提供</i>";
    tr.innerHTML = `<td>${s.sampleIndex}</td>
      <td><b>期望:</b> ${esc(s.expected)}<br><b>实际:</b> ${esc(s.actual)}<br><b>模型:</b> ${esc(s.modelRef)}<br><b>判官:</b> ${esc(s.judgeIdentity)}</td>
      <td class="${cls}">${s.passed ? "PASS" : "FAIL"} (${s.score})</td>
      <td>${usage}</td>
      <td><input data-score="${s.sampleIndex}" type="number" min="0" max="1" step="0.1" value="${annByIndex.get(s.sampleIndex)?.manualScore ?? ""}"></td>
      <td><input data-note="${s.sampleIndex}" placeholder="纠正/备注" value="${esc(annByIndex.get(s.sampleIndex)?.note ?? "")}"></td>`;
    tbody.appendChild(tr);
  }
  const annotate = document.createElement("button");
  annotate.textContent = "保存标注";
  annotate.onclick = async () => {
    const idx = Number(document.querySelector(`[data-score]`)?.dataset.score);
    for (const row of tbody.querySelectorAll("tr")) {
      const sampleIndex = Number(row.querySelector("[data-score]").dataset.score);
      const manualScore = row.querySelector(`[data-score="${sampleIndex}"]`).value;
      const note = row.querySelector(`[data-note="${sampleIndex}"]`).value;
      await fetch(`/api/v1/evaluation-runs/${runId}/annotations`, {
        method: "POST",
        body: JSON.stringify({ sampleIndex, reviewer: "ui", manualScore: manualScore === "" ? null : Number(manualScore), preference: note ? "prefer_corrected" : null, note, correctedOutput: note || null }),
        headers: { "Content-Type": "application/json" },
      });
    }
    alert("标注已保存");
  };
  tbody.parentElement.insertAdjacentElement("afterend", annotate);
});

$("export-btn").addEventListener("click", async () => {
  const runId = $("export-run").value;
  const sampleIndexes = $("export-indexes").value.split(",").map((s) => Number(s.trim()));
  const body = { name: $("export-name").value, runId, sampleIndexes };
  const res = await fetch("/api/v1/feedback-sets", { method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "application/json" } });
  const obj = await json(res);
  $("export-out").textContent = JSON.stringify(obj, null, 2);
  const exp = await fetch(`/api/v1/feedback-sets/${obj.id}/export`, { method: "POST" });
  const expObj = await exp.json();
  $("export-out").textContent += "\\n\\n" + JSON.stringify(expObj, null, 2);
  $("#export-download").href = `/api/v1/feedback-sets/${obj.id}/export`;
  $("#export-actions").hidden = false;
});

function esc(v) { return v == null ? "" : String(v).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]); }
</script>
</body>
</html>
"""
