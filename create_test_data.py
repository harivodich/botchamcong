import pandas as pd
import os

# Đường dẫn file
output_file = os.path.join(os.path.dirname(__file__), "test_timesheet_day4.xlsx")

# Dữ liệu mẫu bám sát kịch bản test
data = {
    "Ngày": ["15/06/2026", "16/06/2026", "17/06/2026", "18/06/2026"],
    "Tên Giáo Viên": ["Vikram", "MAAN", "Sơn Tùng", "SHAN"],
    "Số học viên": [5, 4, 0, 5],
    "Tiền phạt": [0, 0, 0, 0],
    "Ghi chú": ["Lễ x2.5", "Dạy thay x1.5", "Nghỉ phép", "Dạy thay Sơn Tùng"]
}

df = pd.DataFrame(data)

# Xuất ra file Excel
try:
    df.to_excel(output_file, index=False)
    print(f"✅ Đã tạo file Excel thành công tại:\n{output_file}")
except Exception as e:
    print(f"❌ Lỗi tạo file: {e}")
