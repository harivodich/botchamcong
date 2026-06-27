import os
import sys

current_dir = os.path.dirname(__file__)
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from instructor_service.database import get_connection
from payroll_engine.calculator import calculate_mark

def generate_monthly_report(month: int, year: int) -> str:
    """
    Truy vấn cơ sở dữ liệu để lấy toàn bộ ca dạy trong tháng.
    Tính toán tổng số ca, tổng tiền phạt và ước lượng tổng quỹ lương.
    Trả về một chuỗi Markdown để gửi qua Telegram.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Lấy thông tin tất cả các ca dạy trong tháng
    # JOIN với bảng instructors để lấy base_rate
    query = """
        SELECT i.name, i.base_rate, t.student_count, t.penalty_fee, t.note
        FROM teaching_logs t
        JOIN instructors i ON t.instructor_id = i.id
        WHERE EXTRACT(MONTH FROM t.date) = %s AND EXTRACT(YEAR FROM t.date) = %s
    """
    
    try:
        cursor.execute(query, (month, year))
        rows = cursor.fetchall()
        
        if not rows:
            return f"📊 **BÁO CÁO THÁNG {month}/{year}**\n\nKhông có dữ liệu ca dạy nào trong tháng này."
            
        total_classes = len(rows)
        total_students = 0
        total_penalty = 0
        total_payroll = 0
        
        # Thống kê theo loại ca
        ca_x = 0
        ca_07x = 0
        ca_05x = 0
        
        for row in rows:
            name, base_rate, student_count, penalty_fee, note = row
            total_students += student_count
            total_penalty += penalty_fee
            
            base_mark, multiplier = calculate_mark(student_count, note or "")
            
            if base_mark == "X":
                base_value = 1.0
                ca_x += 1
            elif base_mark == "0.7X":
                base_value = 0.7
                ca_07x += 1
            elif base_mark == "0.5X":
                base_value = 0.5
                ca_05x += 1
            else:
                base_value = 0.0
                
            # Tính lương cho ca này
            class_salary = base_rate * base_value * multiplier
            total_payroll += class_salary
            
        # Trừ đi tổng tiền phạt
        total_payroll -= total_penalty
        
        report = (
            f"📊 **BÁO CÁO TỔNG QUAN THÁNG {month}/{year}**\n\n"
            f"💵 **TỔNG QUỸ LƯƠNG DỰ KIẾN:** `{int(total_payroll):,} đ`\n\n"
            f"📈 **Chỉ số hoạt động:**\n"
            f"- Tổng số ca đã dạy: {total_classes} ca\n"
            f"- Tổng số lượt HV đi tập: {total_students} lượt\n"
            f"- Trung bình HV/ca: {total_students/total_classes:.1f} người/ca\n\n"
            f"📉 **Phân loại ca dạy:**\n"
            f"- Số ca X (Chuẩn): {ca_x} ca\n"
            f"- Số ca 0.7X: {ca_07x} ca\n"
            f"- Số ca 0.5X (Mất ca): {ca_05x} ca\n\n"
            f"⚠️ **Chỉ số rủi ro:**\n"
            f"- Tổng tiền phạt vi phạm: `{total_penalty:,} đ`"
        )
        return report
        
    except Exception as e:
        print(f"Lỗi generate_monthly_report: {e}")
        return f"❌ Lỗi truy xuất dữ liệu: {str(e)}"
    finally:
        cursor.close()
        conn.close()

def generate_check_report(month: int, year: int, query_str: str) -> str:
    """
    Tra cứu lương và số ca của một Mã GV, Tên nhóm, hoặc Tên bộ phận.
    """
    conn = get_connection()
    cursor = conn.cursor()
    query_upper = query_str.upper().strip()
    
    query = """
        SELECT i.id, i.name, i.department, i.group_name, i.base_rate, t.student_count, t.penalty_fee, t.note
        FROM teaching_logs t
        JOIN instructors i ON t.instructor_id = i.id
        WHERE EXTRACT(MONTH FROM t.date) = %s AND EXTRACT(YEAR FROM t.date) = %s
        AND (UPPER(i.id) = %s OR UPPER(i.group_name) = %s OR UPPER(i.department) = %s OR UPPER(i.name) LIKE %s)
    """
    try:
        cursor.execute(query, (month, year, query_upper, query_upper, query_upper, f"%{query_upper}%"))
        rows = cursor.fetchall()
        
        if not rows:
            return f"❌ Không tìm thấy dữ liệu chấm công cho `{query_str}` trong tháng {month}/{year}."
            
        total_classes = len(rows)
        total_students = 0
        total_penalty = 0
        total_payroll = 0
        
        ca_x = 0
        ca_07x = 0
        ca_05x = 0
        
        for row in rows:
            ins_id, name, dept, group, base_rate, student_count, penalty_fee, note = row
            total_students += student_count
            total_penalty += penalty_fee
            
            base_mark, multiplier = calculate_mark(student_count, note or "")
            
            if base_mark == "X":
                base_value = 1.0
                ca_x += 1
            elif base_mark == "0.7X":
                base_value = 0.7
                ca_07x += 1
            elif base_mark == "0.5X":
                base_value = 0.5
                ca_05x += 1
            else:
                base_value = 0.0
                
            class_salary = base_rate * base_value * multiplier
            total_payroll += class_salary
            
        total_payroll -= total_penalty
        
        report = (
            f"🔍 **KẾT QUẢ TRA CỨU: `{query_str}` (Tháng {month}/{year})**\n\n"
            f"💰 **Tổng lương:** `{int(total_payroll):,} đ`\n\n"
            f"📊 **Chi tiết ca dạy:**\n"
            f"- Tổng số ca: {total_classes} ca\n"
            f"- Số ca X (Chuẩn): {ca_x} ca\n"
            f"- Số ca 0.7X: {ca_07x} ca\n"
            f"- Số ca 0.5X: {ca_05x} ca\n"
            f"- Lượt HV: {total_students} lượt\n\n"
            f"⚠️ **Phạt vi phạm:** `{total_penalty:,} đ`"
        )
        return report
        
    except Exception as e:
        print(f"Lỗi generate_check_report: {e}")
        return f"❌ Lỗi truy xuất dữ liệu: {str(e)}"
    finally:
        cursor.close()
        conn.close()
