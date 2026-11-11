# Tasks: Quét đầy đủ hơn + giải thích "Xem lại"

## Phase 1: Foundational
- [x] T001 `ADVICE` dict + tham số `akey` cho `add()`; mọi lời gọi `add()` trong `src/don_mac.py` có akey
- [x] T002 `installed_apps()` + `advise_entry(e)`; `make_entry` gắn `risk` + `advice`

## Phase 2: US1 - Lời khuyên (P1) 🎯
- [x] T003 [US1] UI Đề xuất: nhãn rủi ro là nút, nút "Vì sao?", khung lời khuyên 4 phần mở/đóng
- [x] T004 [US1] UI bảng: chấm màu rủi ro cạnh tên; khung xem trước có mục "Có nên xóa?"
- [x] T005 [US1] `tests/test_advice.py`: dmg đã cài → safe; zip đã giải nén → safe; ảnh → careful; cache → safe; mọi item review/careful đủ 4 phần

## Phase 3: US2 - Quét đầy đủ (P1)
- [x] T006 [US2] `walk_home` chế độ (path, full); Library chỉ khi có FDA; gói tính như một mục; gom từ 10 MB
- [x] T007 [US2] Bộ lọc ngưỡng ở tab Tệp lớn (mặc định 50 MB, nhớ lựa chọn)
- [x] T008 [US2] Test: file trong Library/Application Support, OrbStack, .gradle xuất hiện

## Phase 4: US3 - Nhóm mới (P2)
- [x] T009 [US3] `scan_appdata()`: cache Electron + Containers/*/Data/Library/Caches (safe), App Support/Containers ≥ 300 MB (careful, lời khuyên theo app)
- [x] T010 [US3] Test nhóm mới

## Phase 5: Polish
- [x] T011 Chạy lại toàn bộ test 001 + 002, ảnh chụp UI, đóng gói
