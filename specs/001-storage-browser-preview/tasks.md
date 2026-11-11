# Tasks: Quản lý dung lượng kiểu macOS, có xem trước file

**Input**: Design documents from `/specs/001-storage-browser-preview/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md

## Phase 1: Setup

- [x] T001 Tạo `tests/make_fake_home.py`: HOME giả có ảnh PNG, PDF, .txt, .py, .docx giả, file 60 MB, Tải về với atime/mtime 2 năm / 5 tháng / 1 tuần, thư mục lồng nhau, ~/Library/Keychains giả
- [x] T002 Nâng VERSION lên 4.0 trong `src/don_mac.py`

## Phase 2: Foundational (chặn mọi user story)

- [x] T003 Sổ đăng ký `ENTRIES` + hàm `make_entry(path, st)` (id, name, kind, size, mtime, used, is_dir, deletable, preview) trong `src/don_mac.py`
- [x] T004 `deletable(path)` theo research R6 và test trong `tests/test_core.py`
- [x] T005 `enrich_mdls(entries)`: lô mdls Kind + LastUsedDate, lùi về bảng đuôi file + atime
- [x] T006 Mở rộng `do_delete`/`/api/reveal` để nhận id từ `ENTRIES`, xóa xong thì gỡ khỏi mọi danh sách tab
- [x] T007 Khung UI mới: thanh tab segmented, chuyển Đề xuất cũ vào tab, bảng dùng chung (sort, chọn nhiều, ⌘A, ⇧-click, mũi tên), thanh hành động Hiển thị trong Finder / Xóa…

## Phase 3: User Story 1 - Tệp lớn (P1) 🎯 MVP

- [x] T008 [US1] `walk_home` gom file ≥ 50 MB thành `TABS["big"]` (thay nhóm "File lớn" 200 MB ở Đề xuất)
- [x] T009 [US1] `GET /api/tab?name=big`
- [x] T010 [US1] Render tab Tệp lớn với cột Tên/Loại/Truy cập sau cùng/Kích cỡ; ⌘⌫ → xác nhận xóa
- [x] T011 [US1] Test: quét → file 60 MB có trong big; xóa → vào ~/.Trash, biến khỏi tab

## Phase 4: User Story 2 - Xem trước (P1)

- [x] T012 [US2] `GET /api/file` stream + Range 206 + MIME
- [x] T013 [US2] `GET /api/thumb` qua qlmanage + cache; 404 nếu không tạo được
- [x] T014 [US2] `POST /api/text` (64 KB đầu)
- [x] T015 [US2] `POST /api/quicklook` (qlmanage -p)
- [x] T016 [US2] Khung xem trước: image (onerror → thumb), pdf iframe, video/audio, text, thumb, biểu tượng; thông tin file; nhiều mục → tổng; Space → Quick Look; thu gọn khung; responsive
- [x] T017 [US2] Test: /api/file trả đúng byte + Range; /api/text; id lạ → 404

## Phase 5: User Story 3 - Bản tải về (P2)

- [x] T018 [US3] `scan_downloads()`: cấp đầu ~/Downloads, size (du cho thư mục), group theo `used`
- [x] T019 [US3] Render nhóm có tiêu đề + ô chọn cả nhóm
- [x] T020 [US3] Test nhóm đúng theo tuổi

## Phase 6: User Story 4 - Trình duyệt tệp (P2)

- [x] T021 [US4] `POST /api/browse` + DIRSIZE cache + ThreadPool du + pending
- [x] T022 [US4] UI thanh đường dẫn, vào thư mục bằng double-click hoặc dấu ›, tự hỏi lại khi pending > 0, mục không xóa được thì khóa ô chọn
- [x] T023 [US4] Test: browse home → Documents → con; Library không deletable; xóa thư mục con → Thùng rác

## Phase 7: User Story 5 - Đề xuất (P3)

- [x] T024 [US5] Tab Đề xuất giữ đủ nhóm, onboarding quyền, nhắc khởi động lại; test hồi quy xóa một cache

## Phase 8: Polish

- [x] T025 `tests/ui_smoke.js` Playwright: tab, sort, chọn, xem trước ảnh/văn bản, xóa, browse; chụp ảnh sáng/tối
- [x] T026 Chạy quickstart; cập nhật docstring đầu file; copy bản build ra file phân phối

## Dependencies
Setup → Foundational (T003–T007) → US1 → US2 (dùng bảng + ENTRIES) → US3, US4 song song → US5 → Polish.
