import { comparisonMetrics, evaluations, mockAnswer, papers, states } from "./mock-data.js";

const USE_PIPELINE_API = true;
const API_BASE = "/api";

async function request(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) throw new Error(`API pipeline trả về mã lỗi ${response.status}`);
  return response.json();
}

export async function getWorkspace(state) {
  if (USE_PIPELINE_API) {
    try {
      return await request(`/workspace?state=${encodeURIComponent(state)}`);
    } catch (error) {
      console.warn("Không thể kết nối pipeline, chuyển sang dữ liệu mẫu.", error);
    }
  }
  return {
    sourceMode: "Dữ liệu mẫu",
    rawHash: "không có",
    embeddingModel: "dữ liệu mẫu",
    topK: 4,
    state: states[state],
    papers,
    evaluations,
    comparisonMetrics,
  };
}

export async function askResearchQuestion(question, state) {
  if (USE_PIPELINE_API) {
    try {
      return await request("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, state }),
      });
    } catch (error) {
      console.warn("Agent pipeline chưa sẵn sàng, dùng câu trả lời mẫu.", error);
    }
  }
  await new Promise((resolve) => window.setTimeout(resolve, 650));
  return {
    answer: mockAnswer.text,
    sources: mockAnswer.sourceIds.map((index) => papers[index]),
    state,
  };
}
