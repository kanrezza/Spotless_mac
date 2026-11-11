# Feature Specification: Quét đầy đủ hơn + giải thích "Xem lại"

**Feature Branch**: `002-review-advice`

**Created**: 2026-11-05

**Status**: Draft

**Input**: User description: "Tôi thấy vẫn chưa đầy đủ file, cần kiểu những cái nào Xem lại thì khi bấm vào Xem lại thì hiện xóa được gì và vì sao không nên xóa."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Bấm "Xem lại" để biết có nên xóa không (Priority: P1)

Mỗi mục có nhãn **An toàn / Xem lại / Cẩn thận**. Khi người dùng bấm vào nhãn hoặc nút "Vì sao?", một khung giải thích mở ra ngay dưới mục (tab Đề xuất) hoặc trong khung xem trước (các tab bảng). Khung có bốn phần: **Đây là gì**, **✅ Xóa được**, **⚠️ Vì sao nên cân nhắc**, **💡 Nên làm gì**.

**Why this priority**: Người dùng không dám quyết định với các mục "Xem lại". Đây là yêu cầu trực tiếp.

**Independent Test**: Mở tab Đề xuất, bấm nhãn "Xem lại" của "Volume không dùng" (Docker) → thấy giải thích về mất dữ liệu database.

**Acceptance Scenarios**:

1. **Given** một mục bất kỳ ở tab Đề xuất, **When** bấm nhãn rủi ro, **Then** khung giải thích mở/đóng mà không đổi trạng thái ô chọn.
2. **Given** một file .dmg mà ứng dụng tương ứng đã cài trong Ứng dụng, **Then** giải thích ghi rõ "đã cài <tên app>, xóa an toàn" và nhãn là An toàn.
3. **Given** file .zip đã có thư mục giải nén cùng tên bên cạnh, **Then** giải thích ghi "đã giải nén", nhãn An toàn.
4. **Given** ảnh/video/tài liệu cá nhân, **Then** nhãn Cẩn thận và giải thích "không tạo lại được, chỉ xóa khi đã có bản sao".
5. **Given** chọn một mục trong tab bảng, **Then** khung xem trước có mục "Có nên xóa?" cùng nhãn và bốn phần giải thích.

---

### User Story 2 - Thấy đầy đủ file lớn ở mọi nơi trong thư mục người dùng (Priority: P1)

Tab Tệp lớn liệt kê cả file lớn trong ~/Library (dữ liệu app, Containers), OrbStack/Docker, thư mục ẩn (.cache, .gradle…), thư viện Ảnh (tính như một mục). Có bộ lọc ngưỡng: ≥ 10 MB, 50 MB, 100 MB, 500 MB, 1 GB.

**Why this priority**: Người dùng thấy danh sách "chưa đầy đủ". Những chỗ đang bị bỏ qua lại là nơi ăn ổ đĩa nhiều nhất (ví dụ OrbStack 24 GB).

**Independent Test**: HOME giả có ~/Library/Application Support/Zalo/big.db 60 MB và ~/OrbStack/data.img 80 MB → cả hai hiện trong Tệp lớn.

**Acceptance Scenarios**:

1. **Given** file ≥ ngưỡng nằm trong ~/Library, OrbStack hoặc thư mục ẩn, **Then** file xuất hiện trong Tệp lớn.
2. **Given** chọn ngưỡng 500 MB, **Then** chỉ còn file ≥ 500 MB.
3. **Given** chưa có Toàn quyền truy cập ổ đĩa, **Then** không quét ~/Library (tránh hộp thoại hỏi quyền liên tục) và hiện ghi chú vì sao danh sách có thể thiếu.

---

### User Story 3 - Thêm nhóm dọn dẹp còn thiếu (Priority: P2)

Tab Đề xuất có thêm:
- **Cache trong dữ liệu ứng dụng**: các thư mục Cache/Code Cache/GPUCache/Service Worker của app Electron (Discord, Slack, VS Code, Zalo…) và Caches trong Containers. Nhãn An toàn.
- **Dữ liệu ứng dụng lớn**: thư mục ≥ 300 MB trong Application Support / Containers, nhãn Cẩn thận, có hướng dẫn dọn bên trong app (Zalo, Telegram, Chrome, …).

**Independent Test**: HOME giả có Application Support/Slack/Cache 30 MB → mục cache Slack xuất hiện, xóa được.

**Acceptance Scenarios**:

1. **Given** Application Support/<App>/Cache tồn tại, **Then** có mục "<App>: bộ nhớ đệm" An toàn.
2. **Given** Application Support/Zalo ≥ 300 MB, **Then** có mục "Dữ liệu Zalo" Cẩn thận với lời khuyên dọn trong Zalo.

### Edge Cases

- Thư mục không đọc được → bỏ qua, không lỗi.
- Tên app trong file cài đặt không khớp chính xác (pycharm-2026.2.3-aarch64.dmg ↔ PyCharm.app) → so khớp theo từ khóa đầu, không phân biệt hoa thường.
- Mục vừa là cache trong app vừa nằm trong "Dữ liệu ứng dụng lớn" → dung lượng nhóm lớn đã trừ phần cache để không đếm hai lần trong ghi chú.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Mọi mục (tab Đề xuất và các tab bảng) MUST có mức rủi ro và lời khuyên gồm: Đây là gì, Xóa được, Vì sao nên cân nhắc, Nên làm gì.
- **FR-002**: Bấm nhãn rủi ro hoặc nút "Vì sao?" MUST mở/đóng lời khuyên, không thay đổi lựa chọn.
- **FR-003**: Lời khuyên cho file MUST dựa trên loại và vị trí: file cài đặt (đã cài app chưa), file nén (đã giải nén chưa), ảnh/video/tài liệu cá nhân, ảnh đĩa máy ảo, file trong cache, file trong dữ liệu app, thư viện Ảnh, file trong Tải về quá 1 năm.
- **FR-004**: Tab Tệp lớn MUST quét cả ~/Library (khi có quyền), OrbStack và thư mục ẩn; gói (.photoslibrary…) tính như một mục.
- **FR-005**: Tab Tệp lớn MUST có bộ lọc ngưỡng 10 MB / 50 MB / 100 MB / 500 MB / 1 GB (mặc định 50 MB).
- **FR-006**: Tab Đề xuất MUST có nhóm "Cache trong dữ liệu ứng dụng" và "Dữ liệu ứng dụng lớn".
- **FR-007**: Các tab bảng MUST hiện chấm màu mức rủi ro cạnh tên mỗi dòng.

### Key Entities

- **Advice**: risk (safe/review/careful), what, ok (Xóa được), keep (Vì sao nên cân nhắc), tip (Nên làm gì).

## Success Criteria *(mandatory)*

- **SC-001**: 100% mục có nhãn Xem lại/Cẩn thận có lời khuyên đủ 4 phần (kiểm bằng test).
- **SC-002**: Người dùng mở được lời khuyên của một mục trong 1 thao tác.
- **SC-003**: Với HOME giả, Tệp lớn tìm thấy 100% file ≥ ngưỡng đã đặt ở Library, OrbStack, thư mục ẩn.

## Assumptions

- "Chưa đầy đủ file" được hiểu là: các vùng đang bị bỏ qua (Library, OrbStack, thư mục ẩn, dữ liệu app) cần được liệt kê.
- Lời khuyên là quy tắc cố định trong app (không dùng AI/mạng), viết bằng tiếng Việt.
- Hướng dẫn dọn bên trong app nêu chung ("vào Cài đặt của app, mục quản lý bộ nhớ") khi không chắc đường dẫn menu chính xác.
