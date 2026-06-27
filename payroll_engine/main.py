import sys
import os

# Đảm bảo có thể import các module từ thư mục bên ngoài
current_dir = os.path.dirname(__file__)
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from ingestion_service.excel_parser import parse_weekly_timesheet
from payroll_engine.calculator import calculate_mark
from export_service.excel_writer import fill_instructor_works_batch
from instructor_service.database import get_instructor_by_name, add_teaching_log

def process_timesheet(input_filepath: str, file_hash: str | None = None):
    """
    Hàm chính để xử lý một file Excel thô do quản lý đẩy lên.
    """
    print(f"Đang xử lý file: {input_filepath}")
    
    # 1. Đọc dữ liệu từ file thô
    records = parse_weekly_timesheet(input_filepath)
    print(f"Đã đọc được {len(records)} bản ghi hợp lệ.")
    
    # 2. Lặp qua từng bản ghi để tính toán
    error_count = 0
    errors = []
    works_by_month = {}
    
    for record in records:
        day = record["day"]
        month = record["month"]
        year = record["year"]
        instructor_name = record["instructor_name"]
        student_count = record["student_count"]
        penalty_fee = record.get("penalty_fee", 0)
        note = record.get("note", "")
        
        # 2.1. Tra cứu instructor_id từ Database
        instructor = get_instructor_by_name(instructor_name)
        
        # 2.2. Tính công cho Google Sheets và tính thưởng
        base_mark, multiplier = calculate_mark(student_count, note)
        
        # Áp dụng Cách 1: Quy đổi hệ số dôi ra thành Tiền Thưởng (trừ vào penalty_fee)
        if multiplier != 1.0 and base_mark and instructor:
            base_rate = instructor.get("base_rate", 0)
            if base_mark == "X":
                base_value = 1.0
            elif base_mark == "0.7X":
                base_value = 0.7
            elif base_mark == "0.5X":
                base_value = 0.5
            else:
                base_value = 0.0
                
            bonus = int(base_rate * base_value * (multiplier - 1.0))
            if bonus > 0:
                penalty_fee -= bonus
                note = f"{note} (Thưởng: +{bonus:,}đ)"
                
        mark = base_mark

        if instructor:
            instructor_id = instructor["id"]
            date_str = f"{year}-{month:02d}-{day:02d}"
            # Lưu lịch sử ca dạy kèm tiền phạt vào DB
            add_teaching_log(date_str, instructor_id, student_count, penalty_fee, note, file_hash)
        else:
            errors.append(f"Cảnh báo: Giáo viên '{instructor_name}' chưa có trong Database, không lưu được lịch sử và tiền phạt.")
        
        if mark or penalty_fee or note:
            key = (month, year)
            if key not in works_by_month:
                works_by_month[key] = []
                
            works_by_month[key].append({
                "instructor_name": instructor_name,
                "day": day,
                "mark": mark,
                "penalty_fee": penalty_fee,
                "note": note
            })
            
            if not mark and student_count > 0:
                errors.append(f"Ca dạy của {instructor_name} ngày {day}/{month} có {student_count} HV, không đủ tính công (nhưng vẫn lưu phạt/ghi chú).")
        else:
            if student_count > 0:
                errors.append(f"Ca dạy của {instructor_name} ngày {day}/{month} có {student_count} HV, không được tính công.")
            error_count += 1

    # 3. Ghi vào Google Sheets (Batch Update theo từng tháng)
    success_count = 0
    for (month, year), works in works_by_month.items():
        try:
            updated_cells, sheet_errors = fill_instructor_works_batch(month, year, works)
            success_count += len(works) # Số lượng ca được tính
            errors.extend(sheet_errors)
        except Exception as e:
            errors.append(f"Lỗi nghiêm trọng khi ghi dữ liệu tháng {month}/{year}: {str(e)}")

    print(f"Hoàn thành xử lý file.")
    print(f"Thành công: {success_count} ca dạy.")
    print(f"Lỗi/Cảnh báo: {len(errors)}")
    
    return {
        "success": success_count,
        "errors": errors
    }

if __name__ == "__main__":
    # Để test nhanh
    test_file = sys.argv[1] if len(sys.argv) > 1 else None
    if test_file and os.path.exists(test_file):
        process_timesheet(test_file)
    else:
        print("Vui lòng truyền đường dẫn file cần test.")
