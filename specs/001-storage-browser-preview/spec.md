# Feature Specification: Quản lý dung lượng kiểu macOS, có xem trước file

**Feature Branch**: `001-storage-browser-preview`

**Created**: 2026-11-05

**Status**: Draft

**Input**: User description: "Tôi muốn build phần xóa giống cái trong Mac (Cài đặt hệ thống → Dung lượng → Tài liệu: các tab Tệp lớn, Bản tải về, Ứng dụng không được hỗ trợ, Trình duyệt tệp), kiểu nếu là ảnh hoặc tài liệu thì có thể xem trước."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Xem và xóa Tệp lớn như trong macOS (Priority: P1)

Người dùng mở Dọn Mac, chọn tab **Tệp lớn**, thấy một bảng giống hệt màn hình "Tài liệu" của macOS: các cột Tên, Loại, Truy cập sau cùng, Kích cỡ, mặc định sắp xếp theo kích cỡ giảm dần. Họ chọn một hoặc nhiều dòng (click, ⌘-click, ⇧-click), bấm **Xóa…**, xác nhận, và các file được chuyển vào Thùng rác. Nút **Hiển thị trong Finder** mở Finder tại file đang chọn.

**Why this priority**: Đây là thao tác lấy lại dung lượng nhanh nhất và là thứ người dùng đã quen dùng trong macOS; không có nó thì tính năng không có giá trị.

**Independent Test**: Tạo vài file lớn trong thư mục home thử nghiệm, mở tab Tệp lớn, chọn 2 file, xóa → hai file nằm trong Thùng rác và biến mất khỏi bảng.

**Acceptance Scenarios**:

1. **Given** thư mục người dùng có file ≥ 50 MB, **When** mở tab Tệp lớn, **Then** file đó hiện trong bảng với đúng tên, loại, ngày truy cập sau cùng và kích cỡ.
2. **Given** bảng đang hiển thị, **When** bấm vào tiêu đề cột "Kích cỡ" hoặc "Tên", **Then** bảng sắp xếp lại theo cột đó (bấm lần nữa đảo chiều).
3. **Given** đã chọn 3 dòng, **When** bấm Xóa… và xác nhận, **Then** cả 3 file vào Thùng rác, bảng cập nhật và dung lượng trống hiển thị tăng tương ứng sau khi dọn Thùng rác.
4. **Given** chưa chọn dòng nào, **Then** nút Xóa… và Hiển thị trong Finder bị vô hiệu hóa.

---

### User Story 2 - Xem trước ảnh và tài liệu trước khi xóa (Priority: P1)

Khi người dùng chọn một dòng là ảnh, PDF, tài liệu văn phòng (Word, Excel, PowerPoint, Pages, Numbers, Keynote), video, âm thanh hoặc file văn bản/mã nguồn, một khung **xem trước** bên cạnh bảng hiện nội dung file cùng thông tin (đường dẫn, kích cỡ, ngày sửa, ngày truy cập). Nhấn **Space** (hoặc nút "Quick Look") mở cửa sổ Quick Look của macOS để xem toàn màn hình.

**Why this priority**: Người dùng không dám xóa thứ họ không nhận ra; xem trước giúp quyết định nhanh và an toàn (Nguyên tắc II của constitution).

**Independent Test**: Chọn một ảnh JPG, một PDF và một file .docx trong bảng → mỗi file đều hiện hình xem trước trong khung bên cạnh trong vòng 2 giây.

**Acceptance Scenarios**:

1. **Given** dòng được chọn là ảnh (JPG, PNG, GIF, HEIC, WebP…), **Then** khung xem trước hiện chính ảnh đó, vừa khung.
2. **Given** dòng được chọn là PDF, **Then** khung xem trước hiện tài liệu, cuộn được qua các trang.
3. **Given** dòng là tài liệu văn phòng hoặc định dạng khác mà macOS tạo được hình thu nhỏ, **Then** khung hiện hình trang đầu/khung hình đại diện.
4. **Given** dòng là video hoặc âm thanh phổ biến (MP4, MOV, MP3, M4A), **Then** khung hiện trình phát có thể phát thử.
5. **Given** dòng là file văn bản/mã nguồn, **Then** khung hiện nội dung đầu file (tối đa ~200 dòng).
6. **Given** file không xem trước được (ví dụ .dmg), **Then** khung hiện biểu tượng loại file và thông tin, kèm ghi chú "Không có bản xem trước".
7. **Given** chọn nhiều dòng, **Then** khung hiện tổng số mục và tổng dung lượng đã chọn.

---

### User Story 3 - Bản tải về theo độ cũ (Priority: P2)

Tab **Bản tải về** liệt kê các file trong thư mục Tải về, nhóm theo "Cũ hơn 1 năm", "Cũ hơn 3 tháng", "Gần đây" (dựa trên lần truy cập sau cùng), cùng các cột và thao tác như tab Tệp lớn, có xem trước.

**Why this priority**: Thư mục Tải về là nơi tích tụ rác phổ biến nhất sau file lớn.

**Independent Test**: Đặt file với ngày truy cập 2 năm trước và 1 tuần trước vào Tải về → file đầu nằm nhóm "Cũ hơn 1 năm", file sau nằm nhóm "Gần đây".

**Acceptance Scenarios**:

1. **Given** Tải về có file nhiều độ tuổi khác nhau, **When** mở tab, **Then** file được nhóm đúng và trong mỗi nhóm sắp theo kích cỡ.
2. **Given** chọn cả một nhóm bằng ô đánh dấu tiêu đề nhóm, **When** xóa, **Then** mọi file trong nhóm vào Thùng rác.

---

### User Story 4 - Trình duyệt tệp theo dung lượng (Priority: P2)

Tab **Trình duyệt tệp** hiện các thư mục cấp cao trong home kèm dung lượng, sắp xếp lớn → nhỏ. Bấm vào một thư mục để đi sâu vào trong (có thanh đường dẫn để quay lại). File bên trong xem trước và xóa được như các tab khác.

**Why this priority**: Giúp tìm ra "ai đang ăn ổ đĩa" khi các tab kia chưa đủ (ví dụ thư mục OrbStack 24 GB trong ảnh chụp của người dùng).

**Independent Test**: Trong home thử nghiệm có Documents/Project/big.bin → mở Trình duyệt tệp, bấm Documents, bấm Project, thấy big.bin; quay lại bằng thanh đường dẫn.

**Acceptance Scenarios**:

1. **Given** đang ở cấp home, **Then** mỗi thư mục hiển thị dung lượng tổng và có dấu › để vào trong.
2. **Given** đang ở cấp con, **When** bấm phần tử trên thanh đường dẫn, **Then** quay về đúng cấp đó.
3. **Given** chọn một thư mục con (không phải thư mục được bảo vệ), **When** xóa, **Then** thư mục vào Thùng rác.
4. **Given** thư mục được bảo vệ (Documents, Library, …), **Then** không chọn để xóa được, chỉ duyệt vào trong.

---

### User Story 5 - Giữ các mục Đề xuất dọn dẹp hiện có (Priority: P3)

Các nhóm dọn dẹp hiện có (Hệ thống, Ứng dụng, Docker, Thùng rác, công cụ lập trình, simulator, node_modules, cache, sao lưu, log) vẫn có mặt trong tab **Đề xuất**, hoạt động như bản 3.0.

**Why this priority**: Không làm mất tính năng người dùng đã có.

**Independent Test**: Mở tab Đề xuất, thấy các nhóm như trước, xóa một mục cache thành công.

**Acceptance Scenarios**:

1. **Given** bản cập nhật, **When** mở app, **Then** tab Đề xuất hiển thị đủ các nhóm và nút "Chọn tất cả mục An toàn".

---

### Edge Cases

- File bị xóa/di chuyển bên ngoài app sau khi quét → chọn vào thì khung xem trước báo "File không còn tồn tại", xóa thì báo đã không còn.
- Ảnh/PDF rất lớn (hàng trăm MB) → xem trước không làm treo app; dùng hình thu nhỏ thay vì tải nguyên file khi file > 50 MB (trừ video phát trực tiếp).
- Tên file có ký tự tiếng Việt, khoảng trắng, emoji → hiển thị và xem trước đúng.
- Thư mục không có quyền đọc → hiện dung lượng "—" và không vào được, kèm gợi ý cấp quyền.
- Thư mục có hàng chục nghìn file → Trình duyệt tệp vẫn phản hồi; tính dung lượng chạy nền và hiện dần.
- Người dùng nhấn Space khi chưa chọn gì → không làm gì.
- File là symlink → hiển thị nhưng không đi theo liên kết khi tính dung lượng hay xóa.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Hệ thống MUST có các tab: Đề xuất, Tệp lớn, Bản tải về, Trình duyệt tệp.
- **FR-002**: Tab Tệp lớn MUST liệt kê mọi file ≥ 50 MB trong thư mục người dùng (trừ thư viện ảnh/nhạc hệ thống và các vùng đã có ở Đề xuất), với cột Tên, Loại, Truy cập sau cùng, Kích cỡ.
- **FR-003**: Tab Bản tải về MUST liệt kê file trong thư mục Tải về, nhóm theo độ cũ "Cũ hơn 1 năm" / "Cũ hơn 3 tháng" / "Gần đây".
- **FR-004**: Tab Trình duyệt tệp MUST cho duyệt thư mục từ home, hiện dung lượng từng mục, có thanh đường dẫn để quay lại.
- **FR-005**: Mọi bảng MUST sắp xếp được theo từng cột bằng cách bấm tiêu đề cột.
- **FR-006**: Người dùng MUST chọn được nhiều dòng bằng click, ⌘-click, ⇧-click, ⌘A; có ô đánh dấu theo dòng.
- **FR-007**: Mọi tab MUST có nút "Hiển thị trong Finder" và "Xóa…", bị vô hiệu khi chưa chọn.
- **FR-008**: Xóa MUST mặc định chuyển vào Thùng rác và có bước xác nhận nêu số mục và tổng dung lượng; phím ⌘⌫ mở bước xác nhận này.
- **FR-009**: Khung xem trước MUST hiển thị: ảnh trực tiếp; PDF xem được nhiều trang; video/âm thanh phát được; văn bản/mã nguồn hiện nội dung đầu file; định dạng khác dùng hình thu nhỏ do macOS tạo; nếu không có thì hiện biểu tượng loại file.
- **FR-010**: Khung xem trước MUST hiện thông tin file: tên, đường dẫn, kích cỡ, ngày sửa, ngày truy cập sau cùng.
- **FR-011**: Phím Space (và nút "Quick Look") MUST mở cửa sổ Quick Look hệ thống cho file đang chọn.
- **FR-012**: Hệ thống MUST chỉ phục vụ xem trước/xóa cho các mục do chính nó liệt kê; không chấp nhận đường dẫn tùy ý từ giao diện.
- **FR-013**: Thư mục được bảo vệ MUST không xóa được ở mọi tab.
- **FR-014**: Hệ thống MUST giữ nguyên các nhóm dọn dẹp, nhắc khởi động lại và hướng dẫn cấp quyền của bản 3.0 trong tab Đề xuất.
- **FR-015**: Khung xem trước MUST thu gọn được để bảng rộng hơn; trên cửa sổ hẹp khung chuyển xuống dưới bảng.

### Key Entities

- **Mục (Entry)**: một file hoặc thư mục được liệt kê; thuộc tính: id, tên, đường dẫn, loại (mô tả thân thiện), kích cỡ, ngày sửa, ngày truy cập sau cùng, là thư mục hay không, có được bảo vệ không, kiểu xem trước (ảnh/pdf/video/âm thanh/văn bản/hình thu nhỏ/không có).
- **Danh sách tab**: tập Mục của một tab, có thể có nhóm (Bản tải về) và cấp đường dẫn hiện tại (Trình duyệt tệp).
- **Lựa chọn**: tập id Mục đang chọn trong tab hiện tại, cùng tổng dung lượng.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Người dùng tìm và xóa một file lớn không cần thiết trong dưới 30 giây kể từ khi mở tab Tệp lớn.
- **SC-002**: Khung xem trước hiện nội dung trong ≤ 2 giây cho ảnh, PDF và tài liệu văn phòng dưới 50 MB.
- **SC-003**: Bảng 5.000 dòng cuộn và chọn mượt, sắp xếp lại trong dưới 0,5 giây.
- **SC-004**: 100% thao tác xóa ở chế độ mặc định có thể khôi phục từ Thùng rác.
- **SC-005**: Không có trường hợp nào xóa được thư mục được bảo vệ hoặc đường dẫn không do app liệt kê (kiểm chứng bằng kiểm thử tự động).
- **SC-006**: Mở một thư mục trong Trình duyệt tệp hiện danh sách ngay (≤ 1 giây), dung lượng thư mục con hiện dần trong nền.

## Assumptions

- Ngưỡng "Tệp lớn" là 50 MB (macOS hiển thị cả file ~57 MB trong ảnh người dùng gửi).
- "Truy cập sau cùng" lấy từ ngày mở gần nhất do macOS ghi nhận; nếu không có thì dùng ngày truy cập của hệ thống tệp.
- Tab "Ứng dụng không được hỗ trợ" của macOS không làm riêng; phần gỡ ứng dụng đã có trong tab Đề xuất (nhóm Ứng dụng).
- Hình thu nhỏ cho tài liệu văn phòng/video dùng chính bộ Quick Look của macOS nên chỉ có khi chạy trên Mac; trên môi trường khác hiện biểu tượng loại file.
- Ảnh HEIC hiển thị trực tiếp được trong app gốc (WebKit trên macOS hiện tại); nếu không, dùng hình thu nhỏ của hệ thống.
- Phạm vi quét là thư mục người dùng; ổ ngoài và thư mục hệ thống ngoài phạm vi.
