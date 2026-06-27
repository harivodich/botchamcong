import pandas as pd
from typing import List, Dict

def parse_weekly_timesheet(filepath: str) -> List[Dict]:
    """
    Đọc file Excel tuần do Quản lý (Lead) gửi lên.
    Giả định file Excel đầu vào có các cột:
    - Ngày (Định dạng ngày tháng)
    - Tên Giáo Viên
    - Số học viên
    - Tiền phạt (Tùy chọn)
    - Ghi chú (Tùy chọn)
    
    Trả về danh sách các bản ghi để xử lý tiếp.
    """
    try:
        # Đọc file, có thể tuỳ chỉnh header name hoặc index nếu Lead dùng template cố định
        df = pd.read_excel(filepath)
        
        # Chẩn hóa tên cột để dễ truy cập (ví dụ đổi tất cả sang chữ thường, không dấu)
        # Giả định cột có tên chuẩn là 'Ngay', 'Ten Giao Vien', 'So hoc vien'
        # Ở đây ta map cột theo thứ tự để linh hoạt hơn (A=Ngày, B=Tên GV, C=Số HV)
        # hoặc có thể dùng tên cột nếu đã fix template.
        
        records = []
        for index, row in df.iterrows():
            # Tùy chỉnh việc lấy ngày tháng, tên GV, số HV.
            # Lưu ý: Cần xử lý datetime an toàn.
            date_val = row.iloc[0]  # Cột 1: Ngày
            instructor_name = str(row.iloc[1]).strip() # Cột 2: Tên GV
            # Nếu Số học viên bị trống (không có), mặc định là 0
            student_count_val = row.iloc[2]
            if pd.isna(student_count_val) or str(student_count_val).strip() == "":
                student_count = 0
            else:
                try:
                    student_count = int(student_count_val)
                except ValueError:
                    student_count = 0
            
            penalty_fee = 0
            if len(row) > 3 and not pd.isna(row.iloc[3]):
                try:
                    penalty_fee = int(row.iloc[3])
                except ValueError:
                    pass
                    
            note = ""
            if len(row) > 4 and not pd.isna(row.iloc[4]):
                note = str(row.iloc[4]).strip()
                
            # Bỏ qua dòng trống không có Tên GV
            if pd.isna(instructor_name) or instructor_name == 'nan' or instructor_name == '':
                continue
                
            # Trích xuất ngày ra con số (1-31) và tháng năm
            from datetime import datetime
            
            if isinstance(date_val, pd.Timestamp) or isinstance(date_val, datetime):
                day = date_val.day
                month = date_val.month
                year = date_val.year
            elif isinstance(date_val, str):
                date_val = date_val.strip()
                parsed_date = None
                
                # Cố gắng parse theo định dạng Việt Nam phổ biến nhất: dd/mm/yyyy hoặc dd-mm-yyyy
                try:
                    parsed_date = pd.to_datetime(date_val, format="%d/%m/%Y")
                except ValueError:
                    try:
                        parsed_date = pd.to_datetime(date_val, format="%d-%m-%Y")
                    except ValueError:
                        try:
                            # Nếu là chuẩn quốc tế yyyy-mm-dd
                            parsed_date = pd.to_datetime(date_val)
                        except ValueError:
                            pass
                            
                if parsed_date is not None:
                    day = parsed_date.day
                    month = parsed_date.month
                    year = parsed_date.year
                else:
                    continue # Định dạng không hợp lệ
            else:
                continue # Bỏ qua nếu định dạng ngày sai
                
            records.append({
                "day": day,
                "month": month,
                "year": year,
                "instructor_name": instructor_name,
                "student_count": student_count,
                "penalty_fee": penalty_fee,
                "note": note
            })
            
        return records
        
    except Exception as e:
        raise Exception(f"Lỗi khi đọc file timesheet: {str(e)}")
