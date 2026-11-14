# Feature 006: Dọn sâu cho lập trình, hoàn tác, nhiệt độ, mạng, quyền riêng tư (v6.1.0)

- **US1 Hoàn tác lần dọn**: mỗi lần xóa được gắn `batch`; với mục chuyển vào Thùng rác, lịch sử lưu cặp (đường dẫn gốc, đường dẫn trong Thùng rác). Mục “Hoàn tác” gom theo lần dọn và đưa file về đúng chỗ cũ. Bỏ qua: mục đã rời Thùng rác, chỗ cũ đã có tệp khác, mục xóa vĩnh viễn hoặc dọn bằng lệnh. Không ghi đè bất cứ thứ gì; chỉ khôi phục trong thư mục nhà.
- **US2 Dọn sâu (lập trình)** — công cụ `dev2`: Gradle (`caches/modules-2`, `build-cache-1`, `transforms-*`, cache theo phiên bản, `wrapper/dists` giữ bản mới nhất, `daemon`, `native`); Android SDK (system-images, ndk, sources, docs theo từng bản; build-tools giữ 1 bản mới nhất; platforms giữ 2); snapshot của từng máy ảo Android; image Docker không container nào dùng (`docker rmi`), log OrbStack; npm/pnpm/yarn/bun/deno/Puppeteer/Playwright/Electron; pip/uv/Poetry/pre-commit/pyenv; CocoaPods/Rust/SwiftPM; gom node_modules & môi trường ảo quá 120 ngày không sửa. Mỗi mục ≥ 20 MB và luôn có đủ 5 phần giải thích.
- **US3 Nhiệt độ**: `pmset -g therm` (CPU_Speed_Limit, CPU_Scheduler_Limit, CPU_Available_CPUs) + nhiệt độ pin từ ioreg + `kernel_task`. Ba trạng thái Mát / Hơi nóng / Nóng và đang bị chậm lại, kèm app đang đốt CPU và cách hạ nhiệt. Nói rõ macOS không cho đọc nhiệt độ CPU nếu không có quyền quản trị.
- **US4 Mạng theo app**: `nettop -P -x -L 2 -J bytes_in,bytes_out`; hai mẫu liên tiếp cho ra tốc độ hiện tại, mẫu cuối cho tổng từ lúc tiến trình chạy; gom theo app; mẹo theo loại app (trình duyệt, đồng bộ đám mây, container, WARP…).
- **US5 Quyền riêng tư**: đọc TCC.db của người dùng và hệ thống ở chế độ chỉ đọc (`immutable=1`), nhóm theo loại quyền, đánh dấu quyền mạnh và app đã gỡ nhưng còn quyền, mở thẳng trang Cài đặt tương ứng. Cần Toàn quyền truy cập ổ đĩa; không có thì nói rõ. Spotless Mac không bao giờ sửa quyền.

## Kiểm thử
`tests/test_deep.py` (34 kiểm tra), `tests/ui_deep.js`.
