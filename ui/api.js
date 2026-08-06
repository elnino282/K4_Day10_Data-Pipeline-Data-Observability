import { comparisonMetrics, evaluations, mockAnswer, papers, states } from "./mock-data.js";

// Chuyển thành true khi API Python cung cấp các endpoint bên dưới đã sẵn sàng.
const USE_PIPELINE_API = false;
const API_BASE = "http://127.0.0.1:8000/api";

async function request(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) throw new Error(`API pipeline trả về mã lỗi ${response.status}`);
  return response.json();
}

export async function getWorkspace(state) {
  if (USE_PIPELINE_API) return request(`/workspace?state=${encodeURIComponent(state)}`);
  return { state: states[state], papers, evaluations, comparisonMetrics };
}

export async function askResearchQuestion(question, state) {
  if (USE_PIPELINE_API) {
    return request("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, state }),
    });
  }
  await new Promise((resolve) => window.setTimeout(resolve, 650));
  return {
    answer: mockAnswer.text,
    sources: mockAnswer.sourceIds.map((index) => papers[index]),
    state,
  };
}
