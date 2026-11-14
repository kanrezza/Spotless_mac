# Feature 004: Tab Hoạt động (RAM/CPU)

**Yêu cầu**: xem app nào đang ngốn RAM nhiều nhất như Giám sát hoạt động, giải thích vì sao và nên đóng gì; với trình duyệt (ví dụ Brave 4 tab) chỉ ra tab nào ngốn RAM nhất.

## User stories
- **US1**: Thấy Áp lực bộ nhớ, RAM đã dùng (Ứng dụng / Hệ thống giữ cố định / Đã nén), bộ nhớ đệm file, swap, CPU tổng; tự cập nhật mỗi 3 giây, tạm dừng được.
- **US2**: Danh sách app/tiến trình gom helper về app chủ, sắp theo RAM hoặc CPU, tìm kiếm, ẩn tiến trình hệ thống.
- **US3**: Mỗi nhóm có giải thích: Đây là gì, Vì sao tốn RAM/CPU, Nên làm gì, Nên đóng khi nào; bảng tiến trình con (loại, PID, RAM, CPU, CPU trung bình, thời gian chạy).
- **US4**: Phát hiện bất thường: bộ báo cáo sự cố (crashpad) ngốn CPU, tiến trình ngốn CPU liên tục, app chiếm ≥15% RAM; mục “Nên làm gì bây giờ” gợi ý hành động.
- **US5**: Trình duyệt Chromium/Safari: liệt kê tab (AppleScript, chỉ đọc tiêu đề + địa chỉ), xếp hạng theo ước tính loại trang; tùy chọn đo bộ nhớ JS từng tab; đánh dấu “Nên đóng” (nặng mà không xem, mở trùng); Chuyển tới / Đóng tab.
- **US6**: Thoát app (như ⌘Q), Buộc thoát, Buộc dừng tiến trình, luôn hỏi xác nhận; không bao giờ cho dừng tiến trình hệ thống, của người dùng khác hoặc của chính Spotless Mac.

## Ghi chú kỹ thuật
- RAM mỗi tiến trình = `phys_footprint` qua `proc_pid_rusage` (ctypes, libSystem), đúng cột Bộ nhớ của Giám sát hoạt động; không đọc được thì dùng RSS (hiện “≈”).
- RAM máy từ `vm_stat` (Anonymous − purgeable + wired + compressor), áp lực từ `kern.memorystatus_vm_pressure_level`, swap từ `vm.swapusage`.
- `ps` chạy với `LC_ALL=C` để số thập phân dùng dấu chấm.
- macOS không cho biết tab nào ứng với tiến trình renderer nào; đo chính xác dùng `performance.memory.usedJSHeapSize` qua AppleScript (cần bật “Cho phép JavaScript từ Apple Events”).
- Kiểm thử: `tests/test_activity.py`, `tests/ui_activity.js` (dữ liệu giả qua `tests/act_harness.py`).

## Bổ sung v5.3.0
- **US7**: Bấm từng phần của thanh RAM (Ứng dụng, Hệ thống giữ cố định, Đã nén, Bộ nhớ đệm file, Swap) để xem giải thích. Phần Ứng dụng liệt kê các app chiếm RAM kèm câu trả lời “Có nên đóng không?” và số RAM lấy lại được.
- **US8**: Mỗi app có nhãn quyết định: Nên đóng / Có thể đóng / Đang hoạt động / Nhẹ, cứ để / Hệ thống / Có tiến trình kẹt, dựa trên: đang rảnh hay không (CPU ~18 giây gần nhất), dung lượng, loại app (máy ảo, IDE, Docker), áp lực bộ nhớ, mở 2 trình duyệt cùng lúc.
- **US9**: Chi tiết app: % RAM máy, CPU lúc này/trung bình, thời gian chạy, xu hướng RAM (cảnh báo rò rỉ khi tăng đều >100 MB/phút), RAM chia theo loại tiến trình (trang web, tiện ích, GPU…).
