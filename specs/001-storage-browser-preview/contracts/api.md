# HTTP API cục bộ (127.0.0.1, token phiên)

Header `X-Token` bắt buộc cho mọi `/api/*`. Riêng `/api/file` và `/api/thumb` nhận `t=<token>` trong query (thẻ media không gửi được header).

## Có sẵn từ v3.0 (giữ nguyên)
`GET /api/status`, `POST /api/scan|delete|reveal|ping|open_fda|open_orbstack|reveal_app|restart|quit`, `POST /api/bye?t=`

Mở rộng: `/api/delete` và `/api/reveal` nhận id thuộc cả `ITEMS` (Đề xuất) lẫn `ENTRIES` (tab mới).

## Mới

### GET /api/tab?name=big|downloads
→ `200 {"running": bool, "entries": Entry[]}` (xem data-model)

### POST /api/browse `{"id": "<entry id>" | null}`
null = home. → `200 {"dir": Entry, "crumbs": [{"id","name"}], "children": Entry[], "pending": int}`
`pending` = số thư mục con còn đang tính dung lượng. Id không phải thư mục → 404.

### GET /api/file?id=&t=
Stream nội dung file. Hỗ trợ `Range: bytes=a-b` → 206. `Content-Type` theo đuôi file. Thư mục / id lạ → 404.

### GET /api/thumb?id=&t=&s=512|1024
PNG hình thu nhỏ do Quick Look tạo (có cache). Không tạo được → 404 (client hiện biểu tượng).

### POST /api/text `{"id"}`
→ `{"text": str, "truncated": bool}` (tối đa 64 KB, ~200 dòng đầu, UTF-8 thay ký tự lỗi).

### POST /api/quicklook `{"id"}`
Mở cửa sổ Quick Look hệ thống → `{"ok": bool}`.
