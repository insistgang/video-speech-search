const KEY = "video-frame-sample";
const seed = () => ({
  nextId: 10,
  videos: [
    { id: 1, filename: "产品演示.mp4", filepath: "示例/产品演示.mp4", status: "completed", duration: 128, resolution: "1920x1080" },
    { id: 2, filename: "会议录屏.mp4", filepath: "示例/会议录屏.mp4", status: "completed", duration: 246, resolution: "1280x720" }
  ],
  tasks: [
    { id: 1, video_id: 1, video_filename: "产品演示.mp4", status: "completed", stage: "done", progress: 1, frames: 24, skipped: 18, tokens: 0, error: "" },
    { id: 2, video_id: 2, video_filename: "会议录屏.mp4", status: "completed", stage: "done", progress: 1, frames: 18, skipped: 12, tokens: 0, error: "" }
  ],
  keywords: [
    { id: 1, name: "办公软件", category: "应用", terms: ["表格", "导出", "登录"] },
    { id: 2, name: "AI 工具", category: "模型", terms: ["ChatGPT", "Copilot"] }
  ],
  frames: [
    { id: 1, video_id: 1, time: 12.4, app: "浏览器", text: "后台登录页，标题是管理控制台", summary: "画面停留在登录表单，用户名框已填入示例账号。", operation: "打开登录页", ai: false, aiName: "", risk: ["账号输入"], url: "https://example.test/login", code: "", color: "#245c4d" },
    { id: 2, video_id: 1, time: 38.0, app: "表格", text: "导出报表按钮位于右上角", summary: "用户把光标移到导出报表，准备下载本月示例数据。", operation: "悬停导出按钮", ai: false, aiName: "", risk: [], url: "", code: "", color: "#8a6232" },
    { id: 3, video_id: 1, time: 76.5, app: "ChatGPT", text: "请帮我总结这段操作记录", summary: "浏览器里打开了 ChatGPT，输入框中是一条总结请求。", operation: "向对话粘贴文字", ai: true, aiName: "ChatGPT", risk: ["外部对话"], url: "https://example.test/chat", code: "", color: "#314e86" },
    { id: 4, video_id: 2, time: 21.0, app: "会议软件", text: "本周预算讨论", summary: "共享屏幕停在会议议程，第一项是预算讨论。", operation: "共享屏幕", ai: false, aiName: "", risk: [], url: "", code: "", color: "#5a3d6e" },
    { id: 5, video_id: 2, time: 104.2, app: "编辑器", text: "function total(rows) { return rows.length }", summary: "编辑器里能看到一段统计行数的示例函数。", operation: "滚动代码", ai: true, aiName: "Copilot", risk: ["代码可见"], url: "", code: "用数组长度统计行数的示例函数。", color: "#1f4d44" }
  ]
});

let db = seed();
try {
  const saved = JSON.parse(localStorage.getItem(KEY) || "null");
  if (saved && Array.isArray(saved.frames)) db = saved;
} catch (err) { /* keep the built-in sample */ }
function save() { localStorage.setItem(KEY, JSON.stringify(db)); }
const main = document.getElementById("main");
let view = "search";
let detailId = null;
let showHistory = false;
let message = "导入后这里会显示队列进度。";

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}
function videoOf(id) { return db.videos.find((item) => item.id === id); }
function frameOf(id) { return db.frames.find((item) => item.id === Number(id)); }
function thumb(frame) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="${frame.color}"/><text x="32" y="78" fill="#fff7eb" font-size="28" font-family="Georgia,serif">${frame.app}</text><text x="32" y="150" fill="#fff" font-size="34" font-family="PingFang SC,sans-serif">${frame.text.slice(0, 18)}</text><text x="32" y="320" fill="#ffe2b1" font-size="22">${frame.time.toFixed(1)} 秒 · 示例画面</text></svg>`;
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}
function statusText(value) {
  return { completed: "已完成", running: "处理中", pending: "排队中", failed: "失败" }[value] || value;
}
function stageText(value) {
  return { extract: "抽帧", analyze: "画面分析", done: "完成", queue: "排队" }[value] || value || "—";
}
function setNav() {
  document.querySelectorAll(".nav-link").forEach((link) => link.classList.toggle("nav-link-active", link.dataset.view === view));
}
function show(next, id) {
  view = next;
  detailId = id || null;
  if (next !== "detail") location.hash = next;
  setNav();
  render();
}

function render() {
  const pages = { search: renderSearch, import: renderImport, tasks: renderTasks, keywords: renderKeywords, detail: renderDetail };
  main.innerHTML = (pages[view] || renderSearch)();
}
function renderSearch() {
  const options = db.videos.map((item) => `<option value="${item.id}">${esc(item.filename)}</option>`).join("");
  return `<section class="panel-grid">
    <div class="panel panel-wide">
      <p class="eyebrow">检索中心</p>
      <h2>搜索已索引的视频画面内容</h2>
      <form id="search-form" class="search-form">
        <input id="q" placeholder="输入关键词、短语或平台名称；多个词需同时出现" />
        <div class="filter-grid">
          <label>视频<select id="video"><option value="">全部视频</option>${options}</select></label>
          <label>AI 工具检测<select id="ai"><option value="any">全部</option><option value="yes">仅看命中</option><option value="no">仅看未命中</option></select></label>
          <label>起始时间<input id="start" placeholder="0 秒" /></label>
          <label>结束时间<input id="end" placeholder="120 秒" /></label>
        </div>
        <button type="submit">开始检索</button>
      </form>
      <p class="muted">当前为网页示例：可检索内置画面文字，例如 登录、导出、ChatGPT、预算、代码。</p>
      <p id="search-msg" class="muted"></p>
      <div id="search-out"></div>
    </div>
  </section>`;
}
function renderImport() {
  const rows = db.videos.map((item) => `<div class="table-row table-row-videos"><span>${esc(item.filename)}</span><span>${statusText(item.status)}</span><span>${Number(item.duration).toFixed(1)} 秒</span><span>${esc(item.resolution || "-")}</span></div>`).join("");
  const cards = db.tasks.slice(0, 4).map((task) => `<div class="task-progress-card"><div class="task-progress-head"><strong>${esc(task.video_filename)}</strong><span>${statusText(task.status)}</span></div><div class="progress-track"><div class="progress-fill" style="width:${Math.round(task.progress * 100)}%"></div></div><div class="task-progress-meta"><span>进度：${Math.round(task.progress * 100)}%</span><span>阶段：${stageText(task.stage)}</span><span>帧处理：${task.frames}</span></div></div>`).join("");
  return `<section class="panel-grid">
    <div class="panel"><p class="eyebrow">单视频导入</p><h2>导入本地视频</h2>
      <form id="file-form" class="form-stack"><label>视频路径<input id="file-path" placeholder="示例/新的录屏.mp4" /></label>
        <label>处理模式<select id="mode"><option>快速扫描（仅粗扫，零 API 调用）</option><option selected>标准扫描（默认推荐）</option><option>深度扫描（全帧精扫）</option></select></label>
        <button type="submit">导入并排队</button></form></div>
    <div class="panel"><p class="eyebrow">批量导入</p><h2>导入文件夹</h2>
      <form id="folder-form" class="form-stack"><label>文件夹路径<input id="folder-path" placeholder="示例/batch-01" /></label><button type="submit">批量导入</button></form></div>
    <div class="panel panel-wide"><p class="eyebrow">导入状态</p><p>${esc(message)}</p><p class="muted">网页示例不会读取真实路径，只会把名称加入浏览器里的示例库。</p></div>
    <div class="panel panel-wide"><p class="eyebrow">处理进度</p><h2>当前导入任务</h2><div class="task-progress-list">${cards || '<p class="empty">导入后这里会实时显示任务进度。</p>'}</div></div>
    <div class="panel panel-wide"><p class="eyebrow">视频库</p><h2>当前已导入视频</h2><div class="table"><div class="table-row table-head table-row-videos"><span>文件名</span><span>状态</span><span>时长</span><span>分辨率</span></div>${rows}</div></div>
  </section>`;
}
function renderTasks() {
  const list = showHistory ? db.tasks : db.tasks.slice(0, 6);
  const rows = list.map((task) => `<div class="table-row table-row-tasks"><span>${task.id}</span><span>${esc(task.video_filename)}</span><span>${statusText(task.status)}</span><span>${stageText(task.stage)}</span><span>${Math.round(task.progress * 100)}%</span><span>${task.frames}</span><span>${task.skipped}</span><span>${task.tokens}</span><span>${esc(task.error || "无")}</span><span><button class="button-secondary" data-retry="${task.id}" ${task.status === "running" ? "disabled" : ""}>重试</button></span></div>`).join("");
  return `<section class="panel"><p class="eyebrow">处理队列</p><h2>任务列表</h2>
    <div class="action-row"><button class="button-secondary" id="history">${showHistory ? "仅看最新任务" : "显示历史任务"}</button><span class="muted">${showHistory ? `当前展示全部 ${db.tasks.length} 条任务记录` : `当前仅展示最新任务，共 ${list.length} 条`}</span></div>
    <p class="muted">当前为 mock 模式，分析结果来自本地模拟，Token 用量固定为 0。</p>
    <div class="table"><div class="table-row table-head table-row-tasks"><span>ID</span><span>视频</span><span>状态</span><span>阶段</span><span>进度</span><span>帧数</span><span>跳过帧数</span><span>Token 用量</span><span>错误</span><span>操作</span></div>${rows}</div></section>`;
}
function renderKeywords() {
  const cards = db.keywords.map((item) => `<article class="keyword-card"><h3>${esc(item.name)}</h3><p>${esc(item.category)}</p><p>${esc(item.terms.join("，"))}</p><div class="action-row"><button class="button-secondary" data-scan="${item.id}">立即扫描</button><button class="button-secondary" data-del="${item.id}">删除</button></div></article>`).join("");
  return `<section class="panel-grid">
    <div class="panel"><p class="eyebrow">规则词库</p><h2>创建关键词集</h2>
      <form id="key-form" class="form-stack"><label>名称<input id="key-name" /></label><label>分类<input id="key-cat" /></label><label>关键词<input id="key-terms" placeholder="ChatGPT，表格，导出" /></label><button type="submit">保存关键词集</button></form></div>
    <div class="panel panel-wide"><p class="eyebrow">词库列表</p><h2>已有关键词集</h2><div class="keyword-list">${cards || '<p class="empty">当前还没有关键词集。</p>'}</div></div>
    <div class="panel panel-wide" id="scan-box"><p class="eyebrow">扫描结果</p><h2>请选择一个关键词集进行扫描</h2><p class="empty">当前还没有扫描结果。</p></div>
  </section>`;
}
function resultCard(frame) {
  const video = videoOf(frame.video_id);
  return `<a class="result-card" href="#detail-${frame.id}" data-detail="${frame.id}">
    <img class="result-thumb" alt="${esc(video.filename)} 在 ${frame.time.toFixed(1)} 秒处的示例画面" src="${thumb(frame)}" />
    <div><p class="eyebrow">命中结果 <span class="badge badge-source">画面文字</span></p><h3>${esc(video.filename)}</h3><p>${esc(frame.summary)}</p></div>
    <div class="meta"><span>${esc(frame.app)}</span><span>${frame.time.toFixed(1)} 秒</span><span>${frame.ai ? `AI 工具：${esc(frame.aiName)}` : "未明确识别 AI 工具"}</span><span>${frame.risk.length ? esc(frame.risk.join("、")) : "无风险标签"}</span></div>
  </a>`;
}
function renderDetail() {
  const frame = frameOf(detailId) || db.frames[0];
  const video = videoOf(frame.video_id);
  const near = db.frames.filter((item) => item.video_id === frame.video_id);
  return `<section class="panel-grid">
    <div class="panel"><p class="eyebrow">视频信息</p><h2>${esc(video.filename)}</h2><p>${esc(video.filepath)}</p><p>命中时间：${frame.time.toFixed(1)} 秒</p><p class="muted">网页示例没有原视频文件。</p><button class="button-secondary" id="back">返回检索</button></div>
    <div class="panel"><p class="eyebrow">命中画面</p><h2>关键帧预览</h2><img class="detail-frame" alt="关键帧 ${frame.id}" src="${thumb(frame)}" /></div>
    <div class="panel panel-wide"><p class="eyebrow">时间线</p><div class="timeline">${near.map((item) => `<a class="timeline-chip ${item.id === frame.id ? "timeline-chip-active" : ""}" data-detail="${item.id}" href="#detail-${item.id}">${item.time.toFixed(1)} 秒</a>`).join("")}</div></div>
    <div class="panel panel-wide"><p class="eyebrow">结构化分析</p><div class="detail-grid">
      <div class="detail-item"><span class="detail-label">应用 / 网站</span><span>${esc(frame.app)}</span></div>
      <div class="detail-item"><span class="detail-label">AI 工具识别</span><span>${frame.ai ? esc(frame.aiName) : "未识别"}</span></div>
      <div class="detail-item"><span class="detail-label">页面链接</span><span>${esc(frame.url || "未识别到链接")}</span></div>
      <div class="detail-item"><span class="detail-label">风险标签</span><span>${frame.risk.length ? esc(frame.risk.join("、")) : "无"}</span></div>
      <div class="detail-item detail-item-wide"><span class="detail-label">画面摘要</span><span>${esc(frame.summary)}</span></div>
      <div class="detail-item detail-item-wide"><span class="detail-label">操作描述</span><span>${esc(frame.operation)}</span></div>
      <div class="detail-item detail-item-wide"><span class="detail-label">可见文字</span><span>${esc(frame.text)}</span></div>
      <div class="detail-item detail-item-wide"><span class="detail-label">代码摘要</span><span>${esc(frame.code || "未检测到代码")}</span></div>
    </div></div>
  </section>`;
}

function matches(frame, query, videoId, ai, start, end) {
  if (videoId && String(frame.video_id) !== videoId) return false;
  if (ai === "yes" && !frame.ai) return false;
  if (ai === "no" && frame.ai) return false;
  if (start !== "" && frame.time < Number(start)) return false;
  if (end !== "" && frame.time > Number(end)) return false;
  const words = query.split(/\s+/).filter(Boolean);
  const blob = `${frame.text} ${frame.summary} ${frame.app} ${frame.aiName} ${videoOf(frame.video_id).filename}`;
  return words.every((word) => blob.toLowerCase().includes(word.toLowerCase()));
}
function addVideo(name) {
  const id = db.nextId++;
  db.videos.unshift({ id, filename: name, filepath: `示例/${name}`, status: "running", duration: 90, resolution: "1920x1080" });
  db.tasks.unshift({ id: db.nextId++, video_id: id, video_filename: name, status: "running", stage: "extract", progress: 0.35, frames: 8, skipped: 2, tokens: 0, error: "" });
  db.frames.push({ id: db.nextId++, video_id: id, time: 6, app: "桌面", text: `${name} 的示例画面`, summary: "网页示例生成的画面描述，没有真实帧。", operation: "开始播放", ai: false, aiName: "", risk: [], url: "", code: "", color: "#3d5c54" });
  save();
}

document.getElementById("nav").addEventListener("click", (event) => {
  const link = event.target.closest("[data-view]");
  if (!link) return;
  event.preventDefault();
  show(link.dataset.view);
});
main.addEventListener("click", (event) => {
  const detail = event.target.closest("[data-detail]");
  if (detail) { event.preventDefault(); show("detail", detail.dataset.detail); return; }
  if (event.target.id === "back") show("search");
  if (event.target.id === "history") { showHistory = !showHistory; render(); }
  const retry = event.target.closest("[data-retry]");
  if (retry) {
    const task = db.tasks.find((item) => String(item.id) === retry.dataset.retry);
    if (task) { task.status = "running"; task.stage = "analyze"; task.progress = 0.2; task.error = ""; save(); render(); }
  }
  const scan = event.target.closest("[data-scan]");
  if (scan) {
    const set = db.keywords.find((item) => String(item.id) === scan.dataset.scan);
    const hits = db.frames.filter((frame) => set.terms.some((term) => `${frame.text}${frame.summary}${frame.app}`.includes(term)));
    const box = document.getElementById("scan-box");
    box.innerHTML = `<p class="eyebrow">扫描结果</p><h2>${esc(set.name)} 的命中结果</h2><div class="results">${hits.map(resultCard).join("") || '<p class="empty">这个词库没有命中示例画面。</p>'}</div>`;
  }
  const del = event.target.closest("[data-del]");
  if (del) { db.keywords = db.keywords.filter((item) => String(item.id) !== del.dataset.del); save(); render(); }
});
main.addEventListener("submit", (event) => {
  event.preventDefault();
  if (event.target.id === "search-form") {
    const query = document.getElementById("q").value.trim();
    const out = document.getElementById("search-out");
    const msg = document.getElementById("search-msg");
    if (!query) { msg.textContent = "请输入关键词后再检索"; msg.className = "error"; out.innerHTML = ""; return; }
    const hits = db.frames.filter((frame) => matches(frame, query, document.getElementById("video").value, document.getElementById("ai").value, document.getElementById("start").value, document.getElementById("end").value));
    msg.textContent = `结果数：${hits.length}`;
    msg.className = "muted";
    out.innerHTML = hits.length ? `<div class="results">${hits.map(resultCard).join("")}</div>` : `<div class="panel"><p class="eyebrow">暂无结果</p><p>当前没有命中结果。可以试试 登录、导出、ChatGPT、预算、代码。</p></div>`;
  }
  if (event.target.id === "file-form") {
    const path = document.getElementById("file-path").value.trim();
    if (!path) return;
    addVideo(path.split(/[/\\]/).pop());
    message = "已加入示例队列。网页没有读取这个路径。";
    render();
  }
  if (event.target.id === "folder-form") {
    const path = document.getElementById("folder-path").value.trim();
    if (!path) return;
    addVideo("片段-01.mp4");
    addVideo("片段-02.mp4");
    message = `文件夹示例已加入队列：${path}`;
    render();
  }
  if (event.target.id === "key-form") {
    const name = document.getElementById("key-name").value.trim();
    const terms = document.getElementById("key-terms").value.split(/[，,]/).map((item) => item.trim()).filter(Boolean);
    if (!name || !terms.length) return;
    db.keywords.unshift({ id: db.nextId++, name, category: document.getElementById("key-cat").value.trim() || "未分类", terms });
    save();
    render();
  }
});

const initial = location.hash.replace("#", "");
if (initial.startsWith("detail-")) show("detail", initial.slice(7));
else if (["search", "import", "tasks", "keywords"].includes(initial)) show(initial);
else show("search");
