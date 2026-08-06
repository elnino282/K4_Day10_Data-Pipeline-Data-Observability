import { askResearchQuestion, getWorkspace } from "./api.js";

const app = {
  state: "baseline",
  view: "assistant",
  data: null,
  currentSources: [],
  sourceRegistry: new Map(),
  sourceSequence: 0,
  isSubmitting: false,
  lastFocused: null,
};

const labels = {
  assistant: "Trợ lý nghiên cứu",
  observability: "Chất lượng & giám sát",
  documents: "Thư viện bài báo",
  evaluation: "Đánh giá",
};

const escapeHtml = (value) =>
  String(value).replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[character]);

let toastTimer;
function showToast(message) {
  const toast = document.querySelector("#toast");
  toast.textContent = message;
  toast.hidden = false;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => { toast.hidden = true; }, 3200);
}

function registerSources(sources) {
  return sources.map((paper) => {
    const key = `source-${++app.sourceSequence}`;
    app.sourceRegistry.set(key, paper);
    return { key, paper };
  });
}

function bindText(name, value) {
  document.querySelectorAll(`[data-bind="${name}"]`).forEach((element) => {
    element.textContent = value;
  });
}

function bindWidth(name, value) {
  document.querySelectorAll(`[data-bind-style="${name}"]`).forEach((element) => {
    element.style.width = `${value}%`;
  });
}

function renderSources(sourcePapers) {
  const visibleSources = sourcePapers?.length
    ? sourcePapers
    : app.data.sampleSources?.length
      ? app.data.sampleSources
      : app.data.papers.slice(0, 2);
  app.currentSources = visibleSources;
  const entries = registerSources(visibleSources);
  const container = document.querySelector("#source-cards");
  container.innerHTML = entries.map(({ key, paper }, index) => `
    <button class="source-card" type="button" data-source-key="${key}" aria-label="Mở chi tiết nguồn ${index + 1}: ${escapeHtml(paper.title)}">
      <div class="source-number">${index + 1}</div>
      <div>
        <h4>${escapeHtml(paper.title)}</h4>
        <p>${escapeHtml(paper.summary)}</p>
        <div class="source-meta"><span>${escapeHtml(paper.category)}</span><b>Khớp ${Math.round(paper.score * 100)}%</b></div>
      </div>
    </button>
  `).join("");
}

function openSource(key) {
  const paper = app.sourceRegistry.get(key);
  if (!paper) return;
  document.querySelector("#source-modal-title").textContent = paper.title || "Nguồn không có tiêu đề";
  document.querySelector("#source-modal-authors").textContent = paper.authors || "Không rõ tác giả";
  document.querySelector("#source-modal-published").textContent = paper.published || "Không rõ";
  document.querySelector("#source-modal-doi").textContent = paper.id || "Không có";
  document.querySelector("#source-modal-score").textContent = `${Math.round((paper.score || 0) * 100)}%`;
  document.querySelector("#source-modal-retrieved").textContent = paper.retrievedText || paper.summary || "Không có nội dung được lập chỉ mục.";
  document.querySelector("#source-modal-summary").textContent = paper.summary || "Bản ghi Crossref này không có abstract.";
  const link = document.querySelector("#source-modal-link");
  if (paper.url) {
    link.href = paper.url;
    link.hidden = false;
  } else {
    link.removeAttribute("href");
    link.hidden = true;
  }
  const modal = document.querySelector("#source-modal");
  app.lastFocused = document.activeElement;
  modal.hidden = false;
  document.body.classList.add("modal-open");
  modal.querySelector(".source-dialog").focus();
}

function closeSource() {
  document.querySelector("#source-modal").hidden = true;
  document.body.classList.remove("modal-open");
  app.lastFocused?.focus();
}

function renderMetricDecorations(state) {
  const hitBars = document.querySelector("#hit-bars");
  const values = [42, 56, 51, 68, 62, 78, state.hitRate];
  hitBars.innerHTML = values.map((value, index) => `<i style="height:${value}%" class="${index === values.length - 1 ? "active" : ""}"></i>`).join("");

  const dots = document.querySelector("#score-dots");
  dots.innerHTML = [1, 2, 3, 4, 5].map((value) => `<i class="${value <= Math.round(state.judgeScore) ? "filled" : ""}"></i>`).join("");
}

function renderComparison() {
  const chart = document.querySelector("#comparison-chart");
  chart.innerHTML = app.data.comparisonMetrics.map((metric) => `
    <div class="comparison-row">
      <div class="comparison-label"><strong>${metric.label}</strong><span>${metric.baseline}${metric.suffix}</span></div>
      <div class="bar-stack">
        <div><span>Mốc sạch</span><i class="baseline-bar" style="width:${metric.baseline}%"></i><b>${metric.baseline}${metric.suffix}</b></div>
        <div><span>Làm lỗi</span><i class="corrupted-bar" style="width:${metric.corrupted}%"></i><b>${metric.corrupted}${metric.suffix}</b></div>
        <div><span>Sau sửa</span><i class="repaired-bar" style="width:${metric.repaired}%"></i><b>${metric.repaired}${metric.suffix}</b></div>
      </div>
    </div>
  `).join("");
}

function paperStatus(paper) {
  if (app.state === "corrupted" && paper.id.includes("TKDE")) return "issue";
  if (paper.status === "stale") return "stale";
  return "healthy";
}

function renderPapers(query = "") {
  const normalized = query.trim().toLowerCase();
  const filtered = app.data.papers.filter((paper) =>
    [paper.title, paper.authors, paper.id].some((value) => value.toLowerCase().includes(normalized))
  );
  document.querySelector("#search-result-count").textContent = `${filtered.length} kết quả`;
  document.querySelector("#paper-table").innerHTML = `
    <div class="paper-table-header"><span>Bài báo</span><span>Xuất bản</span><span>Chủ đề</span><span>Chất lượng</span><span></span></div>
    ${filtered.map((paper) => {
      const status = paperStatus(paper);
      const statusLabel = status === "issue" ? "Phát hiện lỗi" : status === "stale" ? "Lỗi thời" : "Đạt";
      return `<article class="paper-row">
        <div class="paper-title-cell"><span class="paper-icon">▤</span><div><strong>${escapeHtml(paper.title)}</strong><small>${escapeHtml(paper.authors)} · ${escapeHtml(paper.id)}</small></div></div>
        <time>${paper.published}</time><span>${paper.category}</span><span class="quality-pill ${status}"><i></i>${statusLabel}</span><button type="button" data-url="${escapeHtml(paper.url || "")}" aria-label="Mở bài báo">↗</button>
      </article>`;
    }).join("") || `<div class="empty-state">Không có bài báo khớp với “${escapeHtml(query)}”.</div>`}
  `;
}

function renderEvaluations() {
  document.querySelector("#evaluation-table").innerHTML = `
    <div class="evaluation-row evaluation-header"><span>ID</span><span>Câu hỏi</span><span>Loại</span><span>Truy xuất</span><span>Điểm</span></div>
    ${app.data.evaluations.map((item) => {
      const degraded = app.state === "corrupted" && ["Q-02", "Q-03", "Q-05"].includes(item.id);
      const hit = degraded ? false : item.hit;
      const score = degraded ? Math.max(1, item.score - 2) : item.score;
      return `<div class="evaluation-row"><code>${item.id}</code><strong>${escapeHtml(item.question)}</strong><span>${item.type}</span><span class="result-pill ${hit ? "pass" : "fail"}">${hit ? "Đúng" : "Trượt"}</span><span class="judge-value">${score}.0 <small>/ 5</small></span></div>`;
    }).join("")}
  `;
}

function renderState() {
  const state = app.data.state;
  bindText("collection", state.collection);
  bindText("collectionShort", state.label.toLowerCase());
  bindText("sourceMode", app.data.sourceMode || "Dữ liệu mẫu");
  bindText("rawHash", app.data.rawHash || "không có");
  bindText("embeddingModel", app.data.embeddingModel || "không rõ");
  bindText("topK", app.data.topK || 4);
  bindText("paperCount", state.paperCount);
  bindText("hitRate", `${state.hitRate.toFixed(1)}%`);
  bindText("hitDelta", state.hitDelta);
  bindText("accuracy", `${state.accuracy.toFixed(1)}%`);
  bindText("tokenF1", state.tokenF1.toFixed(2));
  bindText("judgeScore", state.judgeScore.toFixed(1));
  bindText("qualityPassed", state.qualityPassed);
  bindText("qualityTotal", state.qualityTotal);
  bindText("qualityLabel", state.qualityLabel);
  bindText("freshRecords", state.freshRecords);
  bindText("freshLabel", state.freshLabel);
  bindText("trustScore", state.trustScore);
  bindText("trustLabel", state.trustLabel);
  bindText("evaluationCount", app.data.evaluations.length);
  bindWidth("qualityProgress", state.qualityPassed / state.qualityTotal * 100);
  bindWidth("freshProgress", state.freshRecords / state.paperCount * 100);
  document.body.dataset.state = app.state;
  if (app.data.sampleQuestion) {
    document.querySelector("#sample-question").textContent = app.data.sampleQuestion;
  }
  if (app.data.sampleAnswer) {
    document.querySelector("#sample-answer").textContent = app.data.sampleAnswer;
  }
  const sampleSources = app.data.sampleSources?.length
    ? app.data.sampleSources
    : app.data.papers.slice(0, 2);
  const sampleEntries = registerSources(sampleSources);
  bindText("sourceCount", sampleSources.length);
  document.querySelector("#citation-list").innerHTML = sampleEntries.map(({ key, paper }, index) =>
    `<button class="citation-chip" data-source-key="${key}" type="button"><b>${index + 1}</b>${escapeHtml(paper.title)}</button>`
  ).join("");
  renderMetricDecorations(state);
  renderSources(sampleSources);
  renderComparison();
  renderPapers(document.querySelector("#paper-search").value);
  renderEvaluations();
}

async function changeState(stateName) {
  app.state = stateName;
  document.querySelectorAll("[data-state]").forEach((button) => {
    const selected = button.dataset.state === stateName;
    button.classList.toggle("is-active", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
  app.data = await getWorkspace(stateName);
  renderState();
  if (app.data.notice) showToast(app.data.notice);
}

function changeView(viewName) {
  if (!labels[viewName]) return;
  app.view = viewName;
  document.querySelectorAll(".nav-item").forEach((button) => {
    const selected = button.dataset.view === viewName;
    button.classList.toggle("is-active", selected);
    if (selected) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  document.querySelectorAll(".view").forEach((view) => view.classList.toggle("is-active", view.id === `${viewName}-view`));
  document.querySelector("#page-label").textContent = labels[viewName];
  document.body.classList.remove("menu-open");
  if (window.location.hash !== `#${viewName}`) {
    window.history.replaceState(null, "", `#${viewName}`);
  }
}

function addUserMessage(question) {
  const thread = document.querySelector("#chat-thread");
  thread.insertAdjacentHTML("beforeend", `<article class="message user-message"><div class="message-label">Bạn</div><div class="message-body">${escapeHtml(question)}</div></article><article class="message assistant-message thinking-message"><div class="assistant-avatar">P</div><div class="message-content"><div class="message-label">PaperLens</div><div class="thinking"><i></i><i></i><i></i><span>Đang tìm kiếm trong chỉ mục ${escapeHtml(app.data.state.label.toLowerCase())}…</span></div></div></article>`);
  thread.scrollTop = thread.scrollHeight;
}

function setSubmitting(value) {
  app.isSubmitting = value;
  const input = document.querySelector("#question-input");
  const send = document.querySelector(".send-button");
  input.disabled = value;
  send.disabled = value;
  send.setAttribute("aria-label", value ? "Đang tạo câu trả lời" : "Gửi câu hỏi");
  document.querySelector("#chat-thread").setAttribute("aria-busy", String(value));
}

async function submitQuestion(question) {
  const normalized = question.trim();
  const input = document.querySelector("#question-input");
  if (!normalized) {
    input.setAttribute("aria-invalid", "true");
    document.querySelector("#chat-form").classList.add("has-error");
    showToast("Hãy nhập câu hỏi trước khi gửi.");
    input.focus();
    return;
  }
  if (app.isSubmitting) return;
  setSubmitting(true);
  addUserMessage(normalized);
  try {
    const response = await askResearchQuestion(normalized, app.state);
    const entries = registerSources(response.sources);
    document.querySelector(".thinking-message")?.remove();
    document.querySelector("#chat-thread").insertAdjacentHTML("beforeend", `<article class="message assistant-message"><div class="assistant-avatar">P</div><div class="message-content"><div class="message-label">PaperLens <span>Câu trả lời có nguồn</span></div><div class="message-body">${escapeHtml(response.answer)}</div><div class="citation-list">${entries.map(({ key, paper }, index) => `<button class="citation-chip" data-source-key="${key}" type="button"><b>${index + 1}</b>${escapeHtml(paper.title)}</button>`).join("")}</div><div class="message-actions"><button type="button" data-action="copy">Sao chép</button><button type="button" data-action="helpful" aria-pressed="false">Hữu ích</button><button type="button" data-action="unhelpful" aria-pressed="false">Chưa hữu ích</button></div></div></article>`);
    bindText("sourceCount", response.sources.length);
    renderSources(response.sources);
    if (response.notice) showToast(response.notice);
  } catch (error) {
    document.querySelector("#chat-thread").insertAdjacentHTML("beforeend", `<p class="empty-state" role="alert">Không thể tạo câu trả lời lúc này. Vui lòng thử lại.</p>`);
    showToast("Yêu cầu thất bại. Hãy kiểm tra kết nối rồi thử lại.");
  } finally {
    document.querySelector(".thinking-message")?.remove();
    setSubmitting(false);
    input.focus();
    document.querySelector("#chat-thread").scrollTop = document.querySelector("#chat-thread").scrollHeight;
  }
}

function downloadJson(filename, payload) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
  const link = Object.assign(document.createElement("a"), { href: url, download: filename });
  link.click();
  URL.revokeObjectURL(url);
  showToast("Đã chuẩn bị tệp JSON để tải xuống.");
}

document.querySelectorAll(".nav-item").forEach((button) => button.addEventListener("click", () => changeView(button.dataset.view)));
document.querySelectorAll("[data-state]").forEach((button) => button.addEventListener("click", () => changeState(button.dataset.state)));
document.querySelectorAll(".suggestion-row button").forEach((button) => button.addEventListener("click", () => submitQuestion(button.textContent)));
document.querySelector("#paper-search").addEventListener("input", (event) => renderPapers(event.target.value));
document.querySelector("#paper-table").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-url]");
  if (button?.dataset.url) window.open(button.dataset.url, "_blank", "noopener,noreferrer");
});
document.addEventListener("click", async (event) => {
  const sourceButton = event.target.closest("[data-source-key]");
  if (sourceButton) openSource(sourceButton.dataset.sourceKey);
  if (event.target.closest("[data-close-source]")) closeSource();
  const action = event.target.closest("[data-action]");
  if (action?.dataset.action === "copy") {
    try {
      await navigator.clipboard.writeText(action.closest(".message-content").querySelector(".message-body").textContent);
      showToast("Đã sao chép câu trả lời.");
    } catch { showToast("Trình duyệt không cho phép sao chép tự động."); }
  }
  if (["helpful", "unhelpful"].includes(action?.dataset.action)) {
    action.closest(".message-actions").querySelectorAll("[aria-pressed]").forEach((button) => button.setAttribute("aria-pressed", String(button === action)));
    showToast("Cảm ơn phản hồi của bạn.");
  }
});
document.addEventListener("keydown", (event) => {
  const modal = document.querySelector("#source-modal");
  if (modal.hidden) return;
  if (event.key === "Escape") closeSource();
  if (event.key === "Tab") {
    const focusable = [...modal.querySelectorAll('button:not([hidden]), a[href]:not([hidden]), [tabindex="0"]')];
    const first = focusable[0];
    const last = focusable.at(-1);
    if (event.shiftKey && (document.activeElement === first || !focusable.includes(document.activeElement))) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
});
document.querySelector("#chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = document.querySelector("#question-input");
  const question = input.value;
  if (question.trim()) {
    input.value = "";
    input.style.height = "auto";
    document.querySelector("#question-count").textContent = "0/1000";
  }
  await submitQuestion(question);
});
document.querySelector("#question-input").addEventListener("input", (event) => {
  const input = event.target;
  input.removeAttribute("aria-invalid");
  document.querySelector("#chat-form").classList.remove("has-error");
  document.querySelector("#question-count").textContent = `${input.value.length}/1000`;
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 100)}px`;
});
document.querySelector("#question-input").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    event.currentTarget.form.requestSubmit();
  }
});
document.querySelector("#clear-chat").addEventListener("click", () => {
  document.querySelector("#chat-thread").innerHTML = `<div class="empty-chat"><span>✦</span><strong>Bắt đầu cuộc trò chuyện có căn cứ</strong><p>Hỏi về phương pháp, kết quả, tác giả hoặc ngày xuất bản.</p></div>`;
  document.querySelector("#question-input").focus();
  showToast("Đã bắt đầu cuộc trò chuyện mới.");
});
document.querySelector("#export-workspace").addEventListener("click", () => downloadJson(`paperlens-${app.state}.json`, app.data));
document.querySelector("#download-evaluations").addEventListener("click", () => downloadJson(`evaluation-${app.state}.json`, app.data.evaluations));
document.querySelector("#view-evaluation").addEventListener("click", () => changeView("evaluation"));
document.querySelector(".mobile-menu").addEventListener("click", () => document.body.classList.toggle("menu-open"));
document.querySelector(".mobile-overlay").addEventListener("click", () => document.body.classList.remove("menu-open"));
window.addEventListener("hashchange", () => changeView(window.location.hash.slice(1)));

changeState("baseline");
changeView(labels[window.location.hash.slice(1)] ? window.location.hash.slice(1) : "assistant");
