# Implementation Plan: Bộ công cụ mở rộng

**Branch**: `003-more-tools` | **Date**: 2026-11-11 | **Spec**: [spec.md](./spec.md)

## Summary
Giữ kiến trúc một file `src/don_mac.py`. Thêm khối "công cụ": cấu hình + danh sách giữ + lịch sử, bốn trình quét theo yêu cầu (gỡ app, trùng lặp, mồ côi, ảnh giống), thông tin máy/bảo mật chỉ-đọc, chế độ dòng lệnh `--auto-clean`, và hai tab giao diện mới ("Công cụ", "Máy & cài đặt").

## Constitution Check
| Nguyên tắc | Đánh giá |
|---|---|
| I. An toàn dữ liệu | ✅ Mọi xóa qua `do_delete`; chặn xóa hết nhóm trùng; danh sách giữ; auto-clean chỉ nhóm An toàn |
| II. Thấy trước khi xóa | ✅ Xác nhận trước khi xóa, `--dry-run`, giải thích rủi ro cho mồ côi |
| III. Cục bộ | ✅ Không mạng, chỉ stdlib |
| IV. Trải nghiệm macOS | ✅ Cùng bộ tab/segmented, chế độ sáng/tối |
| V. Kiểm chứng | ✅ `tests/test_tools.py` + UI smoke |

## Design
- `DATA_DIR` = `~/Library/Application Support/DonMac` (đã là SUPPORT_DIR); `config.json` {keep:[...], schedule:{...}}; `history.jsonl`.
- `TOOL_ITEMS` sổ đăng ký riêng cho kết quả công cụ (không bị `run_scan` xóa); `do_delete`/`/api/reveal` tra cả `ITEMS`, `ENTRIES`, `TOOL_ITEMS`.
- `TOOLS[name]` = {running, step, done, data, error}; `start_tool(name)` chạy luồng nền. API: `POST /api/tool` (bắt đầu), `GET /api/toolres?name=`.
- Trùng lặp: gom theo size → băm 1 MB đầu → băm toàn bộ (sha256); bỏ hard link; `DUP_GROUPS[gid] = [eid…]` để `do_delete` chặn xóa hết nhóm.
- Mồ côi: tên kiểu bundle-id trong các thư mục Library; "được phủ" nếu trùng/tiền tố với bundle id của app đã cài (app trong /Applications, ~/Applications, /System/Applications, một cấp thư mục con); bỏ `com.apple.*`.
- Ảnh giống: `sips -z 9 9 -s format bmp` → dHash 64-bit; phân cụm union-find, khoảng cách ≤ 5, tối đa 4000 ảnh.
- Lịch: `schedule_set()` ghi LaunchAgent `local.donmac.auto.plist` + `launchctl`; `auto_clean(dry_run, min_mb)`.
- Máy/bảo mật: chạy lệnh chỉ-đọc (`sysctl`, `vm_stat`, `ps`, `pmset`, `fdesetup`, `socketfilterfw`, `csrutil`, `spctl`), đọc plist LaunchAgents.
- Dev artifacts: bảng luật `ARTIFACT_RULES` trong `walk_home` (tên thư mục + file anh em bắt buộc).

## Project Structure
`src/don_mac.py` (thêm), `tests/test_tools.py` (mới), `README.md`, `LICENSE`, `.gitignore`.
