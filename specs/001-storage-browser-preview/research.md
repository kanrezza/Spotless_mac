# Research: Quản lý dung lượng kiểu macOS, có xem trước file

## R1. Tạo hình xem trước cho tài liệu văn phòng, video, định dạng lạ
- **Decision**: `qlmanage -t -s 1024 -o <cache_dir> <file>` tạo `<tên file>.png`. Cache theo id mục, chạy theo yêu cầu, giới hạn 20 s.
- **Rationale**: Dùng đúng bộ Quick Look của macOS nên hỗ trợ mọi định dạng mà Finder xem trước được (docx, xlsx, pptx, pages, numbers, key, mov, psd…). Không cần thư viện.
- **Alternatives**: `sips` chỉ xử lý ảnh. QuickLookThumbnailing qua Swift thì phải thêm cầu nối giữa app và server, phức tạp hơn mà không lợi hơn.

## R2. Hiển thị ảnh/PDF/video trực tiếp
- **Decision**: Endpoint `GET /api/file?id=…&t=…` stream file với `Content-Type` theo đuôi file, hỗ trợ `Range` (206). Ảnh dùng `<img>`, PDF dùng `<iframe>` (WKWebView hiển thị PDF sẵn), video/âm thanh dùng `<video>/<audio>`. Ảnh > 50 MB hoặc ảnh lỗi (`onerror`, ví dụ HEIC trên WebKit cũ) thì lùi về `/api/thumb`.
- **Rationale**: Xem đúng nội dung, tua được video, không tốn RAM.
- **Alternatives**: base64 trong JSON thì quá nặng. Object URL thì mất Range.

## R3. Cột "Loại" và "Truy cập sau cùng" giống macOS
- **Decision**: Gọi `mdls -raw -name kMDItemKind -name kMDItemLastUsedDate f1 f2 …` theo lô 200 file. Kết quả `-raw` cách nhau bằng ký tự NUL, theo thứ tự (Kind, LastUsed) cho từng file. Kind đã được bản địa hóa sẵn ("Ảnh Đĩa", "Tài liệu PDF"). Thiếu thì lùi về bảng đuôi file → tên tiếng Việt và `st_atime`.
- **Rationale**: Khớp chữ hiển thị của Cài đặt hệ thống. Theo lô thì nhanh.
- **Alternatives**: Gọi mdls từng file thì chậm (hàng nghìn tiến trình). Chỉ dùng atime thì không khớp macOS.

## R4. Trình duyệt tệp với dung lượng thư mục
- **Decision**: `browse(id)` trả ngay danh sách con: file lấy kích cỡ từ `lstat().st_blocks`, thư mục có `size=null`. Một ThreadPool tính `du -sk` cho từng thư mục con và ghi vào cache `DIRSIZE`. Client hỏi lại `/api/browse` mỗi giây cho tới khi đủ.
- **Rationale**: Mở thư mục ≤ 1 s (SC-006). Cache giúp quay lại nhanh.
- **Alternatives**: Tính sẵn cả cây thì chậm lần đầu và tốn RAM.

## R5. Quick Look toàn màn hình (phím Space)
- **Decision**: `POST /api/quicklook {id}` chạy `qlmanage -p <file>` nền. Nếu tiến trình trước còn chạy thì terminate nó trước.
- **Rationale**: Có sẵn, đúng trải nghiệm macOS.
- **Alternatives**: Dùng QLPreviewPanel trong app Swift thì phải thêm cầu nối; để dành cho sau.

## R6. Phạm vi được phép xóa khi duyệt tự do
- **Decision**: `deletable(path)` = `is_safe(path)` và không thuộc ~/Library (trừ ~/Library/Caches/*, ~/Library/Logs/*, ~/Library/Developer/*), ~/.ssh, ~/.gnupg, ~/.Trash. Mục không xóa được thì ô chọn bị khóa.
- **Rationale**: Trình duyệt tự do dễ chạm phải Keychains, Mail… (Nguyên tắc I).

## R7. Danh sách lớn
- **Decision**: Render bảng bằng chuỗi HTML một lần, sắp xếp phía client, giới hạn hiển thị 3.000 dòng đầu kèm dòng "và N mục nhỏ hơn…".
- **Rationale**: Đủ SC-003 mà không cần virtual scroll.
