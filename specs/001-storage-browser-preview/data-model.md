# Data Model

## Entry (mục trong bảng)
| Trường | Kiểu | Ghi chú |
|---|---|---|
| id | str (12 hex) | Khóa trong sổ `ENTRIES` |
| name | str | Tên file/thư mục |
| path | str | Đường dẫn tuyệt đối (chỉ server dùng để thao tác; UI chỉ hiển thị) |
| kind | str | Mô tả loại (mdls Kind hoặc bảng đuôi) |
| size | int \| null | Byte trên đĩa; null = đang tính / không rõ |
| mtime | float | Ngày sửa |
| used | float \| null | Truy cập sau cùng (LastUsedDate, lùi về atime) |
| is_dir | bool | |
| deletable | bool | Kết quả `deletable(path)` |
| preview | enum | `image` · `pdf` · `video` · `audio` · `text` · `thumb` · `dir` · `none` |
| group | str \| null | Chỉ tab Bản tải về: `old1y` · `old3m` · `recent` |

**Validation**: Mọi thao tác (file, thumb, text, quicklook, reveal, delete) tra id trong `ENTRIES` hoặc `ITEMS`. Id lạ thì trả 404.

## TabList
- `big`: Entry[] (file ≥ 50 MB) được điền khi quét home.
- `downloads`: Entry[] cấp đầu của ~/Downloads, có `group`.
- `browse`: `{ dir: Entry, crumbs: [{id,name}], children: Entry[], pending: int }`.

## Selection (client)
- Tập id trong tab hiện tại, `anchor` cho ⇧-click. Tổng = Σ size.

## Chuyển trạng thái của Entry
`listed` → (xóa thành công) → bị loại khỏi mọi danh sách và `ENTRIES`.
`listed` → (file biến mất bên ngoài app) → preview/delete trả "không còn tồn tại".
