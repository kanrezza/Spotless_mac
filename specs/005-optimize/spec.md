# Feature 005: Pin & tối ưu (v6.0.0)

**Bối cảnh**: pin tụt khi cắm sạc (củ 20W → 30W), tiến trình `crashpad_handler` kẹt ăn >100% CPU, nhiều tab/app.

## User stories
- **US1 Pin & sạc**: % pin, trạng thái; dòng điện Củ sạc → Máy đang dùng → Pin (W, dấu − khi rút từ pin); kết luận: pin tụt dù cắm sạc / sạc chậm / giữ 80% (sạc tối ưu) / tạm dừng vì nóng / sạc tốt; lời khuyên công suất củ sạc theo MacBook Air/Pro; app tốn điện nhất (Tác động năng lượng từ `top -stats power`, gom về app); sức khỏe pin (dung lượng tối đa, số lần sạc, tình trạng, mAh).
- **US2 Kiểm tra nhanh**: Brave/Chrome/Edge: Tiết kiệm bộ nhớ, tăng tốc phần cứng, chạy nền sau khi đóng, tiện ích nặng/thừa (đọc tên cả dạng `__MSG_…__`); app chạy dạng bản sao tạm (App Translocation) hoặc nằm trong Tải về/Màn hình nền → nút Chuyển vào Ứng dụng; Chế độ nguồn điện thấp; máy chạy lâu + swap lớn → nên khởi động lại; nhiều chương trình chạy nền.
- **US3 Khởi động cùng máy**: LaunchAgent của người dùng: giải thích (trình cập nhật Google/Microsoft/Brave, OrbStack, Docker, WARP, brew services…), Tắt (bootout + cất plist vào `DonMac/disabled_agents`) / Bật lại; mục toàn hệ thống: Hiện trong Finder + mở Cài đặt → Mục đăng nhập; app mở khi đăng nhập (System Events): bỏ / thêm lại.
- **US4 Theo dõi nền** (LaunchAgent `local.donmac.watch`, mỗi 60 giây, CPU tính theo chênh lệch thời gian CPU giữa hai lượt): báo tiến trình ≥ ngưỡng % CPU liên tục ≥ N phút (crashpad ≥ 20%), tùy chọn tự buộc dừng crashpad; báo pin tụt khi cắm sạc; báo thiếu RAM; mỗi loại báo tối đa 30 phút–2 giờ một lần; nhật ký sự kiện.
- **US5 Thanh menu**: app phụ Swift riêng (`DonMac/SpotlessMenu`, LaunchAgent `local.donmac.menu`), lỗi biên dịch không ảnh hưởng app chính; tiêu đề ●/◐/◉ + %CPU, ⚠︎ khi có tiến trình kẹt, ⚡︎ khi pin tụt; menu: RAM, CPU, pin, app nặng nhất, Buộc dừng tiến trình kẹt, Mở Spotless Mac, Ẩn biểu tượng. Dữ liệu qua `don_mac.py --mini`, hành động qua `--mini-act`.
- **US6 Lịch sử**: mẫu mỗi 30 phút (`metrics.jsonl`, giữ 60 ngày); biểu đồ ổ trống, RAM + swap, pin (7/30/60 ngày); dự báo ngày đầy ổ (hồi quy 7 ngày); ổ đầy vì đâu (so sánh nhóm Đề xuất giữa 2 lần quét, `scans.jsonl`); đã dọn theo tuần (từ lịch sử dọn).

## An toàn
- Không đổi cài đặt hệ thống; chỉ mở đúng trang Cài đặt hệ thống (`x-apple.systempreferences:`).
- Tắt LaunchAgent luôn có bản sao lưu để bật lại; không đụng mục toàn hệ thống và mục của Spotless Mac.
- Tự buộc dừng chỉ áp dụng cho bộ báo cáo sự cố; mọi thứ khác chỉ thông báo.

## Kiểm thử
`tests/test_optim.py` (31 kiểm tra, gồm tự buộc dừng một tiến trình thật), `tests/ui_optim.js`.
