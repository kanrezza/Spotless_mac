# Implementation Plan: Quét đầy đủ hơn + giải thích "Xem lại"

**Branch**: `002-review-advice` | **Date**: 2026-11-05 | **Spec**: [spec.md](./spec.md)

## Summary
Thêm bộ quy tắc lời khuyên `advise_entry()` (cho file/thư mục ở tab bảng) và `ADVICE` theo khóa (cho mục Đề xuất).
`walk_home` đi thêm vào các vùng trước đây bỏ qua ở chế độ "chỉ gom file lớn" (Library chỉ khi có FDA).
Thêm hai nhóm Đề xuất: cache trong dữ liệu app và dữ liệu app lớn. UI: nhãn bấm được → khung lời khuyên; chấm rủi ro ở bảng; bộ lọc ngưỡng.

## Technical Context
**Language/Version**: Python ≥ 3.8 stdlib, JS nhúng (như 001) · **Testing**: tests/test_core.py, tests/test_advice.py, tests/ui_smoke.js
**Constraints**: Một file; không mạng; không xin thêm quyền (Library chỉ quét khi đã có FDA)

## Constitution Check
| Nguyên tắc | Đánh giá |
|---|---|
| I. An toàn dữ liệu | ✅ Dữ liệu app lớn gắn Cẩn thận, không đưa vào "Chọn tất cả An toàn"; Containers vẫn theo `deletable()` |
| II. Thấy trước khi xóa | ✅ Đây là mục tiêu tính năng |
| III. Cục bộ | ✅ Quy tắc tĩnh, không mạng |
| IV. Trải nghiệm macOS | ✅ Bộ lọc ngưỡng, chấm màu |
| V. Kiểm chứng | ✅ test_advice.py phủ từng quy tắc |

## Design
- `advise_entry(e)`: thứ tự quy tắc: (1) vị trí: Library/Caches, Containers/*/Caches, App Support Cache dirs → safe; Application Support/Containers khác → careful kèm tên app; OrbStack/Docker.raw/*.img máy ảo → careful; .Trash; (2) gói .photoslibrary → careful "dùng app Ảnh"; (3) loại: .dmg/.pkg/.iso + app đã cài → safe, chưa cài → review; .zip/.rar… có thư mục giải nén → safe, không → review; ảnh/video/âm thanh/tài liệu → careful; mã nguồn → review; (4) tuổi: Tải về > 1 năm nâng "review" ← "careful"? Không: chỉ thêm câu vào tip.
- `installed_apps()`: tập tên app (chữ thường, bỏ khoảng trắng) từ /Applications, ~/Applications, cache 1 lần/lần quét.
- `ADVICE[akey]` cho Đề xuất; `add(..., akey=...)` gắn `advice` vào item. Khóa: trash, tm_snap, app_old, app_recent, sound_lib, docker_images, docker_containers, docker_build, docker_volumes, dev_cache, dev_archives, dev_models, brew, sims_bad, sims_runtime, android_avd, android_img, node_modules, venv, installer, archive, cache, appcache, appdata, backup, logs, dotcache.
- Walk: stack phần tử `(path, full)`; vào vùng skip với `full=False` (chỉ gom file lớn). Gói hậu tố → `du` 1 lần, thêm như mục lớn. Ngưỡng gom 10 MB; client lọc.

## Project Structure
Giữ `src/don_mac.py`; thêm `tests/test_advice.py`.
