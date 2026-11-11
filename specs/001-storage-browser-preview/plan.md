# Implementation Plan: Quản lý dung lượng kiểu macOS, có xem trước file

**Branch**: `001-storage-browser-preview` | **Date**: 2026-11-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-storage-browser-preview/spec.md`

## Summary

Thêm vào Dọn Mac giao diện bốn tab giống Cài đặt hệ thống → Dung lượng (Đề xuất, Tệp lớn, Bản tải về,
Trình duyệt tệp). Các tab dùng chung một bảng sắp xếp được, chọn được nhiều dòng, và một khung xem trước bên phải.
Xem trước lấy thẳng nội dung file (ảnh, PDF, video, âm thanh, văn bản) qua một endpoint stream có hỗ trợ Range.
Các định dạng còn lại dùng hình thu nhỏ do `qlmanage` (Quick Look) tạo, có cache. Space mở Quick Look hệ thống.
Mọi file đi qua sổ đăng ký `ENTRIES` theo id, không nhận đường dẫn từ client. Toàn bộ vẫn nằm trong một file `don_mac.py`.

## Technical Context

**Language/Version**: Python ≥ 3.8 (stdlib), HTML/CSS/JS nhúng; app gốc Swift 5 (đã có từ v3.0, không đổi)
**Primary Dependencies**: Không có gói ngoài. Công cụ macOS: `qlmanage` (thumbnail, Quick Look), `mdls` (Kind + LastUsedDate), `du`, `open -R`
**Storage**: Không có DB. Sổ đăng ký id → mục trong bộ nhớ; cache thumbnail trong thư mục tạm của phiên
**Testing**: Script Python chạy trên HOME giả (Linux/macOS) + Playwright/Chromium headless cho UI
**Target Platform**: macOS 11+ (Apple Silicon/Intel). Logic lõi vẫn chạy được trên Linux để test
**Project Type**: Ứng dụng desktop (web UI cục bộ nhúng trong WKWebView)
**Performance Goals**: Bảng 5.000 dòng sắp xếp < 0,5 s; xem trước ≤ 2 s; mở thư mục ≤ 1 s, dung lượng thư mục con tính nền
**Constraints**: Một file phân phối; chỉ 127.0.0.1 + token; mặc định vào Thùng rác
**Scale/Scope**: Home cỡ vài trăm nghìn file; một người dùng

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Nguyên tắc | Đánh giá | Ghi chú |
|---|---|---|
| I. An toàn dữ liệu | ✅ | Xóa qua `delete_one` hiện có (Thùng rác mặc định), thêm `deletable()` chặn ~/Library (trừ Caches/Logs/Developer), ~/.ssh, ~/.gnupg, thư mục bảo vệ |
| II. Thấy trước khi xóa | ✅ | Đây chính là mục tiêu của tính năng: khung xem trước + thông tin + xác nhận |
| III. Cục bộ, không phụ thuộc | ✅ | Chỉ stdlib + công cụ có sẵn của macOS; endpoint file/thumbnail dùng token phiên trong query (thẻ `<img>`/`<video>` không gửi được header) |
| IV. Trải nghiệm gốc macOS | ✅ | Tab dạng segmented, bảng cột như macOS, Space/⌘⌫/⌘A/⇧-click |
| V. Kiểm chứng được | ✅ | Test Python trên HOME giả + Playwright; `qlmanage`/`mdls` thiếu thì lùi về biểu tượng/atime |

**Post-design re-check**: ✅ Không vi phạm. Thiết kế endpoint ở [contracts/api.md](./contracts/api.md) chỉ nhận id.

## Project Structure

### Documentation (this feature)

```text
specs/001-storage-browser-preview/
├── plan.md              # File này
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/api.md     # Phase 1: HTTP API cục bộ
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
src/
└── don_mac.py           # Toàn bộ app: quét, sổ đăng ký, HTTP API, UI nhúng, Swift shell, bộ cài
tests/
├── make_fake_home.py    # Tạo HOME giả với ảnh/PDF/văn bản/file lớn/Tải về theo tuổi
├── test_core.py         # Test lõi: quét, nhóm, browse, deletable, endpoint file/text/thumb
└── ui_smoke.js          # Playwright: tab, sắp xếp, chọn, xem trước, xóa
```

**Structure Decision**: Giữ một file `src/don_mac.py` (Nguyên tắc III: phân phối một file). Test để riêng ở `tests/`.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Token trong query string cho `/api/file`, `/api/thumb` | Thẻ `<img>`, `<video>`, `<iframe>` không đặt được header `X-Token` | Tải blob qua fetch rồi tạo object URL thì video lớn phải nạp hết vào RAM, mất khả năng tua (Range) |
