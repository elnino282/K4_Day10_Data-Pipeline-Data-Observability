# Giao diện PaperLens

Giao diện mẫu cho lab RAG và giám sát dữ liệu Ngày 10. Giao diện không cần cài thêm thư viện và hiện đọc dữ liệu mẫu cố định thông qua `api.js`.

## Chạy trên máy

Từ thư mục gốc của dự án:

```powershell
python script/run_ui.py
```

Sau đó mở <http://127.0.0.1:4173>.

## Điểm nối với pipeline

Server tích hợp hiện cung cấp:

- `GET /api/workspace?state=baseline|corrupted|repaired`
- `POST /api/chat` với `{ "question": "...", "state": "baseline" }`

Dashboard đọc trực tiếp artifact clean, answers, metrics, quality và freshness. Chat tải hoặc dựng Chroma collection theo trạng thái rồi gọi RAG agent. API key luôn nằm ở phía máy chủ; trình duyệt không bao giờ đọc `.env`.

Có thể đổi địa chỉ bằng `UI_HOST` và `UI_PORT` trong `.env`. Nếu chỉ chạy static server, giao diện tự chuyển sang dữ liệu mẫu vì không có `/api`.
