# Bộ Test Cases (Kịch bản kiểm thử) Sản phẩm Gym Payroll Bot (Phiên bản FSM & Cloud)

Dưới đây là danh sách đầy đủ các kịch bản để bạn kiểm tra toàn diện hệ thống trước khi chính thức Deploy lên Cloud Run. Hãy chạy thử trên máy tính của bạn trước (`python api_gateway/bot.py`).

---

## Nhóm 1: Kiểm tra Bảo mật & Phân quyền (Security Test)
**Mục đích:** Đảm bảo người lạ không thể sử dụng Bot nội bộ.

- **Test Case 1.1: Người lạ chat với Bot**
   - **Thao tác:** Nhờ một người khác (không nằm trong danh sách `ADMIN_IDS`) vào Bot gõ `/start`.
   - **Kết quả mong đợi:** Bot hiện câu chào mừng bình thường, nhưng **không hiển thị đường link Google Sheets** (như thiết kế mới).
- **Test Case 1.2: Người lạ cố tình gọi lệnh Admin**
   - **Thao tác:** Nhờ người đó gõ thử `/add_gv`, `/list_gv` hoặc ném 1 file Excel vào Bot.
   - **Kết quả mong đợi:** Bot chặn ngay lập tức và báo: `❌ Lỗi: Bạn không có quyền thực hiện lệnh này!` (Hoặc bạn không có quyền upload file).

---

## Nhóm 2: Trải nghiệm Hỏi - Đáp FSM (Quản lý Giáo viên)
**Mục đích:** Kiểm tra luồng hội thoại nhập liệu FSM mới, đảm bảo không bị lỗi vặt và chống crash hệ thống.

- **Test Case 2.1: Thêm giáo viên mới (Happy Path)**
   - **Thao tác:** Gõ `/add_gv`. Sau đó trả lời lần lượt các câu hỏi của Bot: nhập mã (VD: `GV999`), nhập Tên, nhập Bộ phận (VD: `YOGA`), nhóm, chức danh, giá (VD: `250000`).
   - **Kết quả mong đợi:** Bot thông báo thành công. Mở file Sheets ra xem có thấy GV mới xuất hiện đúng vị trí không.
- **Test Case 2.2: Phá bĩnh Bot (Crash Test)**
   - **Thao tác:** Gõ `/add_gv`. Khi Bot hỏi "Nhập Tên Giáo Viên", bạn cố tình không gõ chữ mà **gửi 1 bức ảnh** hoặc **gửi 1 file tài liệu**.
   - **Kết quả mong đợi:** Bot không bị crash. Nó sẽ cảnh báo `❌ Vui lòng nhập bằng văn bản!` và đứng yên chờ bạn nhập lại tên đàng hoàng.
- **Test Case 2.3: Sửa thông tin thông minh (Edit)**
   - **Thao tác:** Gõ `/edit_gv`. Nhập mã `GV999`. Khi Bot hỏi tên mới, bạn gõ dấu `-` để giữ nguyên. Khi Bot hỏi đơn giá, bạn gõ `500000`.
   - **Kết quả mong đợi:** Bot đồng bộ Google Sheets và chỉ thay đổi duy nhất Đơn giá thành `500000`, tên vẫn giữ nguyên.
- **Test Case 2.4: Lệnh Hủy ngang (/cancel)**
   - **Thao tác:** Gõ `/add_gv` hoặc `/edit_gv`. Ở giữa chừng, đổi ý và gõ `/cancel`.
   - **Kết quả mong đợi:** Bot báo `✅ Đã hủy bỏ thao tác hiện tại.` Bạn có thể dùng các lệnh khác bình thường, không bị kẹt ở trạng thái Hỏi - Đáp cũ.
- **Test Case 2.5: Xóa có xác nhận an toàn**
   - **Thao tác:** Gõ `/del_gv`. Nhập `GV999`. Bot hỏi có chắc chắn xóa không, gõ một từ bất kỳ (VD: `NO`).
   - **Kết quả mong đợi:** Bot báo hủy lệnh xóa. Dữ liệu của GV999 vẫn an toàn trên DB và Sheets.

---

## Nhóm 3: Luồng Chấm Công & Xử Lý Nền (Background Processing)
**Mục đích:** Kiểm tra cơ chế chống Timeout Webhook và xử lý file Excel chuẩn xác.

- **Test Case 3.1: Nạp file Excel hợp lệ**
   - **Thao tác:** Gửi 1 file Excel bảng công vào cửa sổ chat.
   - **Kết quả mong đợi:** Bot phản hồi **CỰC NHANH** câu *"⏳ Đang tiếp nhận file và đưa vào hàng chờ xử lý..."* (đây là bằng chứng Background Task hoạt động). Sau đó vài giây, bot mới gửi thông báo tính toán xong.
- **Test Case 3.2: Chống nhân đôi lương (Duplicate File)**
   - **Thao tác:** Forward lại đúng file Excel vừa tải ở Test 3.1 vào Bot một lần nữa.
   - **Kết quả mong đợi:** Bot từ chối ngay lập tức: `❌ Lỗi: File này đã được gửi và tính công trước đó rồi. Hệ thống từ chối xử lý để chống nhân đôi lương!`.
- **Test Case 3.3: Lệnh Hoàn tác (Undo)**
   - **Thao tác:** Gõ `/undo`. Khi bot hỏi mã file, dán mã Hash của file (hiển thị trong thông báo test 3.1) vào.
   - **Kết quả mong đợi:** Bot thu hồi toàn bộ số ca đã cộng trên Google Sheets (xoá các dấu X) và xóa lịch sử trong DB.

---

## Nhóm 4: Báo Cáo & Che giấu lỗi hệ thống
**Mục đích:** Kiểm tra các thông báo lỗi đã được làm thân thiện thay vì văng Raw Exception.

- **Test Case 4.1: Tra cứu thần tốc (/check)**
   - **Thao tác:** Gõ `/check`. Khi bot hỏi Tháng/Năm, gõ chữ `nay`. Khi bot hỏi Từ khóa, gõ `GV01` hoặc `YOGA`.
   - **Kết quả mong đợi:** Ra báo cáo thống kê các ca dạy chuẩn xác của tháng hiện tại mà không cần gõ ngày tháng.
- **Test Case 4.2: Cố tình gõ sai định dạng (/report)**
   - **Thao tác:** Gõ `/report`. Khi bot hỏi Tháng/Năm, gõ linh tinh (VD: `thang_nam`).
   - **Kết quả mong đợi:** Bot nhắc nhở nhẹ nhàng: `❌ Lỗi: Tháng và Năm phải là số! Vui lòng nhập lại:` và đứng chờ bạn gõ lại đàng hoàng.

---

## Nhóm 5: Thử nghiệm Chốt sổ (Close)
- **Test Case 5.1: Khoá bảng công (/close)**
   - **Thao tác:** Gõ `/close`. Bot sẽ hỏi Tháng/Năm cần khóa. Gõ `06 2026` hoặc `06/2026`.
   - **Kết quả mong đợi:** Bot báo khoá thành công. Trên Google Sheets, trang tính tháng 6 xuất hiện biểu tượng 🔒 (Protected), Admin không có quyền (hoặc nhân viên được share link) cũng không thể ấn gõ chữ vào các ô bị khóa.

**Lưu ý:**
Nếu bạn test trơn tru toàn bộ 5 Nhóm trên ở máy tính, thì khi vứt code này lên Cloud Run, nó sẽ chạy giống y hệt 100%. Bạn có thể tự tin bàn giao!
