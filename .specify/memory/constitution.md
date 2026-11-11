<!--
Sync Impact Report
- Version change: (template) → 1.0.0
- Principles defined: I. An toàn dữ liệu trước hết; II. Người dùng luôn thấy trước khi xóa;
  III. Chạy cục bộ, không phụ thuộc; IV. Trải nghiệm gốc macOS; V. Kiểm chứng được
- Added sections: Ràng buộc kỹ thuật, Quy trình phát triển
- Templates: plan-template.md ✅ (Constitution Check đọc file này lúc chạy), spec/tasks templates ✅ không cần sửa
- Follow-up TODOs: none
-->
# Spotless Mac Constitution

## Core Principles

### I. An toàn dữ liệu trước hết (KHÔNG THƯƠNG LƯỢNG)
- Mặc định mọi thao tác xóa file/thư mục là **chuyển vào Thùng rác**; xóa vĩnh viễn chỉ khi người dùng chọn rõ ràng.
- Chỉ xóa đúng mục mà tool đã quét và hiển thị; không bao giờ xóa đường dẫn do trình duyệt/client tự gửi lên.
- Danh sách thư mục được bảo vệ (Home, Library, Documents, Desktop, Downloads, …) không bao giờ bị xóa nguyên thư mục.
- Mọi hành động không khôi phục được (lệnh Docker, snapshot, dọn Thùng rác) phải ghi rõ "xóa vĩnh viễn" trước khi xác nhận.

### II. Người dùng luôn thấy trước khi xóa
- Mỗi mục hiển thị tên, đường dẫn, dung lượng, ngày truy cập/sửa và mức rủi ro.
- File có thể xem trước (ảnh, PDF, tài liệu văn phòng, video, văn bản) phải xem trước được ngay trong app trước khi quyết định.
- Không có thao tác xóa nào xảy ra mà không có bước xác nhận cuối cùng liệt kê số mục và tổng dung lượng.

### III. Chạy cục bộ, không phụ thuộc
- Chỉ dùng thư viện chuẩn Python và công cụ có sẵn trên macOS (qlmanage, mdls, du, osascript, swiftc từ Command Line Tools).
- Không gửi dữ liệu ra khỏi máy; server chỉ nghe 127.0.0.1 và yêu cầu token ngẫu nhiên mỗi phiên.
- Toàn bộ sản phẩm phân phối dưới dạng **một file** `don_mac.py` tự cài thành app.

### IV. Trải nghiệm gốc macOS
- Giao diện bám theo ngôn ngữ của Cài đặt hệ thống → Dung lượng: tab, bảng cột Tên/Loại/Truy cập sau cùng/Kích cỡ, nút "Hiển thị trong Finder" và "Xóa…".
- Phím tắt quen thuộc: Space để xem trước (Quick Look), ⌘⌫ để xóa, ⌘A chọn tất cả, ⇧/⌘-click chọn nhiều.
- Hỗ trợ chế độ sáng/tối; văn bản giao diện bằng tiếng Việt.

### V. Kiểm chứng được
- Logic quét/xóa phải chạy được trên thư mục home giả (biến môi trường HOME) để kiểm thử tự động trên mọi hệ điều hành.
- Mỗi tính năng mới có ít nhất một kịch bản kiểm thử tự động (Python) và một kiểm thử giao diện bằng trình duyệt headless.
- Phần chỉ chạy được trên macOS phải có đường lùi an toàn khi công cụ hệ thống không có.

## Ràng buộc kỹ thuật
- Python ≥ 3.8, không cài thêm gói. Giao diện là HTML/CSS/JS nhúng, không framework, không CDN.
- Hiệu năng: danh sách phải hiển thị mượt với ≥ 5.000 dòng; ảnh xem trước tạo theo yêu cầu và được cache.
- Ảnh xem trước chỉ phục vụ cho mục đã quét (tham chiếu bằng id), không nhận đường dẫn tùy ý.

## Quy trình phát triển
- Mọi tính năng đi qua Spec Kit: specify → (clarify) → plan → tasks → implement.
- Trước khi giao: chạy bộ kiểm thử Python + kiểm thử giao diện, cập nhật số phiên bản.

## Governance
Constitution này đứng trên mọi quy ước khác của dự án. Sửa đổi phải ghi lý do, tăng phiên bản theo semver
(MAJOR: bỏ/đổi nghĩa nguyên tắc; MINOR: thêm nguyên tắc/mục; PATCH: diễn đạt). Mỗi plan phải có mục
Constitution Check đối chiếu năm nguyên tắc trên; vi phạm phải được ghi vào Complexity Tracking kèm lý do.

**Version**: 1.0.0 | **Ratified**: 2026-11-05 | **Last Amended**: 2026-11-05
