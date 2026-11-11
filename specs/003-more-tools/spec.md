# Feature Specification: Bộ công cụ mở rộng (trùng lặp, gỡ app sạch, dữ liệu mồ côi…)

**Feature Branch**: `003-more-tools`
**Created**: 2026-11-11
**Status**: Implemented
**Input**: "Phát triển thêm: tìm file trùng, gỡ app sạch, dữ liệu mồ côi, danh sách giữ lại, lịch sử, dọn theo lịch, dọn thư mục build của dự án, ảnh giống nhau, trạng thái máy, kiểm tra bảo mật cơ bản. Không làm cập nhật app qua Homebrew cask."

## User Scenarios & Testing

### US1 - Tìm và dọn file trùng lặp (P1)
Người dùng mở **Công cụ → Trùng lặp**, bấm "Quét". Danh sách hiện theo nhóm các file có nội dung giống hệt nhau (so bằng băm nội dung, không chỉ so tên). Mỗi nhóm có một bản được đề xuất giữ lại; các bản còn lại được tích sẵn.
1. **Given** hai file cùng nội dung ở hai thư mục, **Then** chúng nằm chung một nhóm, dung lượng "có thể thu hồi" = size × (số bản − 1).
2. **Given** hai file cùng dung lượng nhưng khác nội dung, **Then** không nằm chung nhóm.
3. **Given** người dùng chọn xóa mọi bản trong một nhóm, **Then** hệ thống từ chối bản cuối cùng ("giữ lại ít nhất một bản").
4. Hard link tới cùng một inode không được tính là trùng (không tiết kiệm được dung lượng).

### US2 - Gỡ ứng dụng cùng dữ liệu đi kèm (P1)
**Công cụ → Gỡ app** liệt kê mọi app đã cài, kèm dung lượng app + dữ liệu đi kèm trong Library và lần mở gần nhất; chọn rồi xóa sẽ chuyển app và dữ liệu đi kèm vào Thùng rác. App hệ thống của Apple và chính Spotless Mac không nằm trong danh sách.

### US3 - Dữ liệu mồ côi của app đã gỡ (P1)
**Công cụ → Dữ liệu mồ côi** liệt kê thư mục/tệp trong Library mang tên kiểu `com.hang.ungdung` mà không có app nào đang cài tương ứng. Mức rủi ro **Xem lại**, có giải thích. Cần Toàn quyền truy cập ổ đĩa để thấy đủ.

### US4 - "Luôn giữ" (whitelist) (P1)
Chọn mục ở bất kỳ tab nào → **Luôn giữ**. Mục (và mọi thứ bên trong) không còn bị đề xuất xóa và mọi thao tác xóa đều từ chối nó. Quản lý/bỏ giữ trong **Máy & cài đặt**.

### US5 - Lịch sử dọn dẹp (P2)
Mọi lần xóa thành công được ghi lại (thời gian, tên, dung lượng, cách xóa, nguồn: tay/tự động). Xem trong **Máy & cài đặt**; có thể xóa lịch sử.

### US6 - Dọn tự động theo lịch (P2)
Bật lịch hằng tuần trong **Máy & cài đặt**. Tác vụ chạy nền (`--auto-clean`) chỉ dọn mục **An toàn** thuộc nhóm bộ nhớ đệm, nhật ký, file cài đặt đã cài app, cache công cụ; chuyển vào Thùng rác khi có thể; bỏ qua mục trong danh sách giữ; chỉ chạy nếu tổng ≥ ngưỡng. Có `--dry-run` để xem trước. Mọi lần chạy được ghi lịch sử.

### US7 - Dọn thư mục build của dự án (P2)
Mở rộng nhóm node_modules/venv: Rust `target` (cạnh Cargo.toml), `Pods` (cạnh Podfile), `.next`, `.nuxt`, `.dart_tool`, `build` của Flutter/Gradle (cạnh pubspec.yaml / build.gradle). Rủi ro **Xem lại**, nói rõ cách tạo lại.

### US8 - Ảnh giống nhau (P3)
**Công cụ → Ảnh giống** nhóm các ảnh trông tương tự (băm cảm nhận 64-bit qua `sips`, khoảng cách Hamming ≤ 5). Chỉ để xem và tự chọn; không tích sẵn.

### US9 - Máy & bảo mật (P3)
**Máy & cài đặt** hiển thị chỉ-đọc: tải CPU, RAM, thời gian chạy, pin; tiến trình ngốn tài nguyên; mục tự khởi động (LaunchAgents/Daemons); FileVault, Tường lửa, SIP, Gatekeeper, phiên bản XProtect. Không có nút thay đổi cài đặt hệ thống. Không phải phần mềm diệt virus.

### US10 - Dấu vết của công cụ AI (P2)
**Công cụ → Dấu vết AI** liệt kê, theo nhóm Claude Code / Claude Desktop / Codex / ChatGPT: bản cài cũ (giữ bản mới nhất và bản đang dùng), transcript `.jsonl`, file-history, log, ảnh/đính kèm cũ hơn N ngày (xóa vĩnh viễn, chỉ file cũ), máy ảo Cowork `vm_bundles` (Cẩn thận), cache app. Không đụng `settings.json`, `CLAUDE.md`, `memory/`, `auth.json`, `config.toml`. `prune_old` chỉ chạy trên thư mục nằm trong danh sách cho phép.

### US11 - Chọn cả nhóm (P2)
Mỗi nhóm trùng lặp/ảnh giống/Dấu vết AI có ô chọn cả nhóm; Ảnh giống có thêm "Chọn tất cả ảnh" và "Chọn tất cả trừ ảnh lớn nhất mỗi nhóm". Với nhóm trùng lặp, ô nhóm chọn các bản thừa (giữ bản đề xuất).

## Requirements

- **FR-001** Mọi thao tác xóa mới đi qua `do_delete` / `delete_one` (cùng kiểm tra an toàn, mặc định Thùng rác).
- **FR-002** API chỉ nhận id do server cấp, không nhận đường dẫn từ client (riêng “Bỏ giữ” chỉ nhận đường dẫn đã có sẵn trong danh sách giữ; cài đặt lịch không có đường dẫn).
- **FR-003** `do_delete` MUST từ chối xóa toàn bộ thành viên của một nhóm trùng lặp.
- **FR-004** Danh sách giữ lưu tại `~/Library/Application Support/DonMac/config.json`; mục bị giữ MUST không xóa được kể cả khi cha/con của nó bị chọn.
- **FR-005** Lịch sử lưu dạng JSON Lines tại `…/DonMac/history.jsonl`; lỗi ghi lịch sử không làm hỏng thao tác xóa.
- **FR-006** `--auto-clean` MUST chỉ chạm nhóm trong danh sách trắng AUTO_CATS với risk=safe, kind path/clear_dir.
- **FR-007** Không có chức năng cập nhật app qua Homebrew cask, không đổi cài đặt hệ thống (chỉ đọc).
- **FR-008** Chỉ dùng thư viện chuẩn Python; chạy cục bộ; không gửi dữ liệu ra ngoài.

## Success Criteria
- SC-001: Với HOME giả, tìm đúng 100% nhóm trùng đã gieo và 0 nhóm sai.
- SC-002: Dữ liệu mồ côi không bao giờ gồm thư mục của app đang cài (test).
- SC-003: Xóa toàn bộ nhóm trùng bị chặn ở bản cuối (test).
- SC-004: `--auto-clean --dry-run` không thay đổi file nào (test).

## Assumptions
- Gỡ app dùng lại cơ chế Thùng rác/Finder của bản 4.x.
- Băm ảnh dùng `sips` có sẵn trên macOS; trên máy không có `sips` thì công cụ này báo "không khả dụng".
- Lịch chạy bằng LaunchAgent của người dùng; tác vụ nền có thể không có Toàn quyền truy cập ổ đĩa nên bỏ qua ~/Library nhạy cảm.
