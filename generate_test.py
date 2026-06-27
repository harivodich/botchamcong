import os
import sys
import pandas as pd
import random
from datetime import datetime, timedelta

current_dir = os.path.dirname(__file__)
if current_dir not in sys.path:
    sys.path.append(current_dir)

from instructor_service.database import get_all_instructors

def generate_data():
    print("Đang lấy danh sách giáo viên từ Database...")
    instructors = get_all_instructors()
    if not instructors:
        print("Chưa có giáo viên nào trong Database!")
        return

    # Lọc ra những người có tên bị trùng đã được sửa (có số ở đuôi, vd: RAHUL 1) 
    # và thêm một số giáo viên ngẫu nhiên để làm dữ liệu phong phú.
    
    start_date = datetime(2026, 6, 1)
    end_date = datetime(2026, 6, 30)
    
    records = []
    
    print(f"Đang tạo dữ liệu cho {len(instructors)} giáo viên...")
    
    for ins in instructors:
        # Mỗi giáo viên dạy ngẫu nhiên từ 5 đến 15 buổi trong tháng
        num_classes = random.randint(5, 15)
        
        for _ in range(num_classes):
            # Chọn ngày ngẫu nhiên
            random_days = random.randint(0, (end_date - start_date).days)
            class_date = start_date + timedelta(days=random_days)
            
            # Số học viên ngẫu nhiên
            # 60% khả năng >= 5 (X)
            # 20% khả năng = 4 (0.7X)
            # 20% khả năng <= 3 (0.5X)
            rand_val = random.random()
            if rand_val < 0.6:
                students = random.randint(5, 20)
            elif rand_val < 0.8:
                students = 4
            else:
                students = random.randint(1, 3)
                
            # Phạt ngẫu nhiên (10% khả năng bị phạt)
            penalty = 0
            if random.random() < 0.1:
                penalty = random.choice([50000, 100000])
                
            # Ghi chú ngẫu nhiên
            note = ""
            if penalty > 0:
                note = "Đi trễ"
            elif students < 5 and random.random() < 0.5:
                note = "Lớp vắng"
                
            records.append({
                "Ngày": class_date.strftime("%d/%m/%Y"),
                "Tên Giáo Viên": ins["name"],
                "Số học viên": students,
                "Tiền phạt": penalty if penalty > 0 else "",
                "Ghi chú": note
            })
            
    # Xáo trộn các record để mô phỏng dữ liệu thực tế (các ngày và tên lộn xộn)
    random.shuffle(records)
    
    df = pd.DataFrame(records)
    output_path = os.path.join(current_dir, "massive_test_v2.xlsx")
    
    # Có thể bị lỗi nếu file đang mở, nên thử bắt lỗi
    try:
        df.to_excel(output_path, index=False)
        print(f"\nHoàn tất! Đã tạo thành công {len(records)} dòng dữ liệu mẫu.")
        print(f"File lưu tại: {output_path}")
    except PermissionError:
        print(f"LỖI: Không thể ghi file {output_path}. Vui lòng đóng file Excel trước khi chạy.")

if __name__ == "__main__":
    generate_data()
