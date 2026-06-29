import os
import tempfile
from typing import Any

import pandas as pd
from openpyxl.styles import Alignment, Font

from instructor_service.database import get_connection
from payroll_engine.calculator import calculate_class_pay


def generate_payroll_excel(month: int, year: int) -> str | None:
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        SELECT i.id AS ins_id, i.name, i.department, i.group_name, i.title, i.base_rate,
               t.student_count, t.penalty_fee, t.note
        FROM instructors i
        LEFT JOIN teaching_logs t ON i.id = t.instructor_id
             AND EXTRACT(MONTH FROM t.date) = %s AND EXTRACT(YEAR FROM t.date) = %s
        ORDER BY i.department, i.group_name, i.name
    """

    try:
        cursor.execute(query, (month, year))
        rows = cursor.fetchall()
        instructor_stats: dict[str, dict[str, Any]] = {}

        for row in rows:
            ins_id, name, dept, group, title, base_rate, student_count, penalty_fee, note = row
            if ins_id not in instructor_stats:
                instructor_stats[ins_id] = {
                    "Ma GV": ins_id,
                    "Ten GV": name,
                    "Bo phan": dept,
                    "Nhom": group,
                    "Chuc danh": title,
                    "Don gia": base_rate,
                    "Tong so ca": 0,
                    "Ca X": 0,
                    "Ca 0.7X": 0,
                    "Ca 0.5X": 0,
                    "Ca 0 HV": 0,
                    "Tong phat": 0,
                    "Tong luong": 0.0,
                }

            if student_count is None:
                continue

            stats = instructor_stats[ins_id]
            penalty = int(penalty_fee or 0)
            pay = calculate_class_pay(int(base_rate or 0), int(student_count), penalty, str(note or ""))

            stats["Tong so ca"] += 1
            stats["Tong phat"] += penalty
            stats["Tong luong"] += pay["gross_salary"]

            if pay["mark"] == "X":
                stats["Ca X"] += 1
            elif pay["mark"] == "0.7X":
                stats["Ca 0.7X"] += 1
            elif pay["mark"] == "0.5X":
                stats["Ca 0.5X"] += 1
            else:
                stats["Ca 0 HV"] += 1

        active_instructors = [
            stats for stats in instructor_stats.values()
            if stats["Tong so ca"] > 0
        ]
        if not active_instructors:
            return None

        for stats in active_instructors:
            stats["Thuc nhan"] = stats["Tong luong"] - stats["Tong phat"]

        columns = [
            "Ma GV", "Ten GV", "Bo phan", "Nhom", "Chuc danh", "Don gia",
            "Tong so ca", "Ca X", "Ca 0.7X", "Ca 0.5X", "Ca 0 HV",
            "Tong luong", "Tong phat", "Thuc nhan",
        ]
        df = pd.DataFrame(active_instructors)[columns]
        
        # Sắp xếp theo Mã GV tăng dần
        df = df.sort_values(by="Ma GV", ascending=True)
        
        file_path = os.path.join(tempfile.gettempdir(), f"Bang_Luong_T{month}_{year}.xlsx")

        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            sheet_name = f"Luong T{month}-{year}"
            df.to_excel(writer, index=False, sheet_name=sheet_name)
            worksheet = writer.sheets[sheet_name]
            
            # Format header
            for col_idx in range(1, len(df.columns) + 1):
                cell = worksheet.cell(row=1, column=col_idx)
                cell.font = Font(bold=True)
                cell.alignment = Alignment(horizontal="center", vertical="center")
            
            # Định dạng các cột tiền (F=6, L=12, M=13, N=14)
            money_cols = {6, 12, 13, 14}
            
            # Căn chỉnh lề tự động và format số tiền
            for col_cells in worksheet.columns:
                max_length = 0
                col_letter = col_cells[0].column_letter
                col_idx = col_cells[0].column
                
                for cell in col_cells:
                    try:
                        if cell.value is not None:
                            # Ước lượng độ rộng của chuỗi
                            cell_len = len(str(cell.value))
                            # Cho thêm tí khoảng trống đối với các cột số tiền do dấu phẩy
                            if col_idx in money_cols:
                                cell_len += 3
                            if cell_len > max_length:
                                max_length = cell_len
                    except Exception:
                        pass
                        
                    # Format hàng ngàn cho các dòng dữ liệu (trừ header)
                    if cell.row > 1 and col_idx in money_cols:
                        cell.number_format = '#,##0'
                        
                worksheet.column_dimensions[col_letter].width = max_length + 2

        return file_path
    except Exception as exc:
        print(f"generate_payroll_excel error: {exc}")
        return None
    finally:
        cursor.close()
        conn.close()
