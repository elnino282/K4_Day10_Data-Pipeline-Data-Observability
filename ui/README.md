# Giao diện PaperLens

Giao diện mẫu cho lab RAG và giám sát dữ liệu Ngày 10. Giao diện không cần cài thêm thư viện và hiện đọc dữ liệu mẫu cố định thông qua `api.js`.

## Chạy trên máy

Từ thư mục gốc của dự án:

```powershell
python -m http.server 4173 --directory ui
```

Sau đó mở <http://127.0.0.1:4173>.

## Điểm nối với pipeline

Khi API Python đã sẵn sàng, đặt `USE_PIPELINE_API = true` trong `api.js` và cung cấp:

- `GET /api/workspace?state=baseline|corrupted|repaired`
- `POST /api/chat` với `{ "question": "...", "state": "baseline" }`

Phản hồi workspace cần có `state`, `papers`, `evaluations` và `comparisonMetrics`. Phản hồi chat cần có `answer`, `sources` và `state`. API key luôn nằm ở phía máy chủ; trình duyệt không bao giờ đọc `.env`.
