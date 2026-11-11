# Tasks: Bộ công cụ mở rộng

## Phase 1: Nền
- [x] T001 `DATA_DIR`, cấu hình, danh sách giữ (`keep_conflict`), `deletable()` + `make_entry` gắn `kept`
- [x] T002 Lịch sử `log_history`/`read_history`, nối vào `do_delete`
- [x] T003 `TOOL_ITEMS`, `TOOLS`, `start_tool`, API `/api/tool`, `/api/toolres`, `/api/keep`, `/api/kept`, `/api/history`

## Phase 2: Công cụ
- [x] T004 [US2] `scan_uninstall()` (Gỡ app)
- [x] T005 [US1] `scan_dupes()` + chặn xóa hết nhóm trong `do_delete`
- [x] T006 [US3] `scan_orphans()`
- [x] T007 [US8] `scan_similar()` + `bmp_dhash()`
- [x] T008 [US7] `ARTIFACT_RULES` trong `walk_home`

## Phase 3: Máy & lịch
- [x] T009 [US9] `machine_info()`, `security_info()`, `startup_items()`, API `/api/machine`
- [x] T010 [US6] `auto_clean()`, `schedule_get/set()`, CLI `--auto-clean/--dry-run/--min-mb`, API `/api/schedule`

## Phase 4: Giao diện
- [x] T011 Tab "Công cụ" (4 công cụ con) và "Máy & cài đặt"; nút "Luôn giữ" ở thanh dưới

## Phase 5: Kiểm chứng & hoàn thiện
- [x] T012 `tests/test_tools.py`, chạy lại test_core + test_advice, ui_smoke
- [x] T013 README, LICENSE, .gitignore, VERSION 5.0, đóng gói

## Phase 6: Bổ sung (Dấu vết AI, chọn cả nhóm)
- [x] T014 [US10] `scan_ai()`, `prune_old()`, `prune_rules()`, `old_versions()`; kind `prune_old` trong `delete_one`
- [x] T015 [US10] Tab con "Dấu vết AI" (nhóm theo công cụ)
- [x] T016 [US11] Ô chọn cả nhóm + nút chọn nhanh cho Ảnh giống
- [x] T017 Test: 20 kiểm tra mới trong tests/test_tools.py, ui_tools.js
