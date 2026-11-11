# Quickstart: kiểm chứng tính năng

## Tự động (Linux hoặc macOS)
```bash
python3 tests/make_fake_home.py /tmp/fh        # ảnh PNG, PDF, .txt, file 60 MB, Tải về với ngày cũ
HOME=/tmp/fh python3 tests/test_core.py        # kỳ vọng: "ALL CORE TESTS PASSED"
node tests/ui_smoke.js                         # kỳ vọng: "UI SMOKE PASSED" + ảnh chụp tests/out/*.png
```

## Thủ công trên Mac
1. `python3 src/don_mac.py --install` rồi mở Dọn Mac.
2. Tab **Tệp lớn**: thấy file ≥ 50 MB; bấm cột Kích cỡ để đảo chiều sắp xếp.
3. Chọn một ảnh thì khung phải hiện ảnh. Chọn PDF thì đọc được trang. Chọn .docx thì hiện trang đầu. Nhấn Space thì Quick Look mở.
4. Chọn 2 dòng, nhấn ⌘⌫ rồi xác nhận: hai file nằm trong Thùng rác.
5. Tab **Bản tải về**: file nhóm theo "Cũ hơn 1 năm / 3 tháng / Gần đây".
6. Tab **Trình duyệt tệp**: vào OrbStack, thấy dung lượng hiện dần; thanh đường dẫn quay lại được; Library không chọn để xóa được.
