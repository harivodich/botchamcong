from .sheet_manager import get_or_create_monthly_sheet

def fill_instructor_works_batch(month: int, year: int, works: list):
    """
    Điền dấu chấm công hàng loạt (Batch Update) lên Google Sheets để tránh bị chặn API.
    works: list of dict, mỗi dict có dạng: 
           {"instructor_name": "...", "day": 1, "mark": "X"}
    """
    if not works:
        return 0, []
        
    worksheet = get_or_create_monthly_sheet(month, year)
    
    # 1. Tải toàn bộ dữ liệu hiện tại về 1 lần duy nhất để đọc (tránh limit read)
    all_values = worksheet.get_all_values()
    
    # Tìm kiếm ánh xạ từ Tên GV sang Row Index
    # Tên GV ở cột C (index 2 trong mảng python)
    name_counts = {}
    for r_idx, row_data in enumerate(all_values):
        if r_idx < 5:  # Bỏ qua header
            continue
        if len(row_data) > 2:
            name = str(row_data[2]).strip().lower()
            if name:
                name_counts[name] = name_counts.get(name, 0) + 1

    name_counters = {}
    name_to_row = {}
    for r_idx, row_data in enumerate(all_values):
        if r_idx < 5:  # Bỏ qua 5 dòng header đầu tiên
            continue
            
        if len(row_data) > 2: # Ít nhất có Cột C
            name = str(row_data[2]).strip().lower()
            if name:
                if name_counts[name] > 1:
                    name_counters[name] = name_counters.get(name, 0) + 1
                    final_name = f"{name} {name_counters[name]}"
                else:
                    final_name = name
                name_to_row[final_name] = r_idx + 1 # Row index trên GG Sheets bắt đầu từ 1
                
    # 2. Xử lý logic gộp ca cho từng người, từng ngày
    # Sử dụng dictionary để lưu trữ giá trị ô sẽ update: {(row, col): "X, 0.5X"}
    cell_updates = {}
    errors = []
    
    for w in works:
        ins_name = w["instructor_name"].strip().lower()
        day = w["day"]
        mark = w["mark"]
        
        target_row = name_to_row.get(ins_name)
        if not target_row:
            errors.append(f"Không tìm thấy giáo viên '{w['instructor_name']}' trên sheet.")
            continue
            
        penalty_fee = w.get("penalty_fee", 0)
        note = w.get("note", "").strip()
        
        # 2.1. Cập nhật dấu công
        if mark:
            target_col = 15 + day # Ngày 1 ở cột P (Cột 16)
            if (target_row, target_col) in cell_updates:
                current_value = cell_updates[(target_row, target_col)]
            else:
                r_py = target_row - 1
                c_py = target_col - 1
                if r_py < len(all_values) and c_py < len(all_values[r_py]):
                    current_value = str(all_values[r_py][c_py]).strip()
                else:
                    current_value = ""
                    
            if current_value:
                if mark == "X" and current_value == "X":
                    new_value = "XX"
                elif mark == "X" and current_value == "XX":
                    new_value = "XXX"
                else:
                    new_value = f"{current_value}, {mark}"
            else:
                new_value = mark
                
            cell_updates[(target_row, target_col)] = new_value

        # 2.2. Cập nhật Tiền Phạt (Cột F - Index 5)
        if penalty_fee:
            if (target_row, 6) in cell_updates:
                current_penalty_str = str(cell_updates[(target_row, 6)])
            else:
                r_py = target_row - 1
                c_py = 5 # Tiền phạt Cột F (Index 5)
                if r_py < len(all_values) and c_py < len(all_values[r_py]):
                    current_penalty_str = str(all_values[r_py][c_py]).replace('.', '').replace(',', '').strip()
                else:
                    current_penalty_str = "0"
            
            if not current_penalty_str.lstrip("-").isdigit():
                current_penalty_str = "0"
            
            new_penalty = int(current_penalty_str) + penalty_fee
            cell_updates[(target_row, 6)] = new_penalty

        # 2.3. Cập nhật Ghi Chú (Cột G - Index 6)
        if note:
            formatted_note = f"Ngày {day}: {note}"
            if (target_row, 7) in cell_updates:
                current_note = str(cell_updates[(target_row, 7)])
            else:
                r_py = target_row - 1
                c_py = 6
                if r_py < len(all_values) and c_py < len(all_values[r_py]):
                    current_note = str(all_values[r_py][c_py]).strip()
                else:
                    current_note = ""
                    
            if current_note:
                new_note = f"{current_note}, {formatted_note}"
            else:
                new_note = formatted_note
                
            cell_updates[(target_row, 7)] = new_note
        
    # 3. Đẩy toàn bộ dữ liệu lên Google Sheets trong 1 lần (Batch Update)
    if cell_updates:
        # Chuyển đổi format cho gspread batch_update
        # [{"range": "O6", "values": [["X"]]}, ...]
        data_to_update = []
        for (r, c), val in cell_updates.items():
            # Dùng hàm có sẵn để đổi sang chữ cái (Cột 15 -> 'O')
            # Vì ta biết max là cột AU (31 ngày), viết hàm nhỏ để map
            data_to_update.append({
                "range": f"{col_num_to_letter(c)}{r}",
                "values": [[val]]
            })
            
        worksheet.batch_update(data_to_update)
        
    return len(cell_updates), errors

def col_num_to_letter(n: int) -> str:
    """Đổi số thứ tự cột thành chữ cái (Ví dụ: 1->A, 27->AA)"""
    string = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        string = chr(65 + remainder) + string
    return string

def rollback_instructor_works_batch(month: int, year: int, works: list):
    """
    Thu hồi dấu chấm công hàng loạt từ Google Sheets dựa trên lịch sử ca dạy.
    """
    if not works:
        return 0, []
        
    worksheet = get_or_create_monthly_sheet(month, year)
    all_values = worksheet.get_all_values()
    
    # Tìm kiếm ánh xạ từ Tên GV sang Row Index
    name_counts = {}
    for r_idx, row_data in enumerate(all_values):
        if r_idx < 5:
            continue
        if len(row_data) > 2:
            name = str(row_data[2]).strip().lower()
            if name:
                name_counts[name] = name_counts.get(name, 0) + 1

    name_counters = {}
    name_to_row = {}
    for r_idx, row_data in enumerate(all_values):
        if r_idx < 5:
            continue
        if len(row_data) > 2:
            name = str(row_data[2]).strip().lower()
            if name:
                if name_counts[name] > 1:
                    name_counters[name] = name_counters.get(name, 0) + 1
                    final_name = f"{name} {name_counters[name]}"
                else:
                    final_name = name
                name_to_row[final_name] = r_idx + 1

    cell_updates = {}
    errors = []
    
    for w in works:
        ins_name = w["instructor_name"].strip().lower()
        # date_val in db is usually datetime.date
        from datetime import date
        if isinstance(w["date"], date):
            day = w["date"].day
        else:
            day = int(str(w["date"]).split("-")[-1])
            
        student_count = w["student_count"]
        penalty_fee = w.get("penalty_fee", 0)
        note = w.get("note", "").strip()
        
        # Calculate the mark that was added
        from payroll_engine.calculator import calculate_mark
        base_mark, multiplier = calculate_mark(student_count, note)
        mark = base_mark
        
        target_row = name_to_row.get(ins_name)
        if not target_row:
            continue
            
        # 1. Rollback dấu công
        if mark:
            target_col = 15 + day
            if (target_row, target_col) in cell_updates:
                current_value = str(cell_updates[(target_row, target_col)])
            else:
                r_py = target_row - 1
                c_py = target_col - 1
                if r_py < len(all_values) and c_py < len(all_values[r_py]):
                    current_value = str(all_values[r_py][c_py]).strip()
                else:
                    current_value = ""
                    
            if current_value:
                if mark == "X" and current_value == "XXX":
                    new_value = "XX"
                elif mark == "X" and current_value == "XX":
                    new_value = "X"
                elif mark == "X" and current_value == "X":
                    new_value = ""
                else:
                    parts = [p.strip() for p in current_value.split(',')]
                    if mark in parts:
                        parts.remove(mark)
                    new_value = ", ".join(parts) if parts else ""
            else:
                new_value = ""
                
            cell_updates[(target_row, target_col)] = new_value

        # 2. Rollback Tiền Phạt
        if penalty_fee:
            if (target_row, 6) in cell_updates:
                current_penalty_str = str(cell_updates[(target_row, 6)])
            else:
                r_py = target_row - 1
                c_py = 5
                if r_py < len(all_values) and c_py < len(all_values[r_py]):
                    current_penalty_str = str(all_values[r_py][c_py]).replace('.', '').replace(',', '').strip()
                else:
                    current_penalty_str = "0"
            
            if not current_penalty_str.lstrip("-").isdigit():
                current_penalty_str = "0"
            
            new_penalty = int(current_penalty_str) - penalty_fee
            cell_updates[(target_row, 6)] = new_penalty

        # 3. Rollback Ghi Chú
        if note:
            formatted_note = f"Ngày {day}: {note}"
            if (target_row, 7) in cell_updates:
                current_note = str(cell_updates[(target_row, 7)])
            else:
                r_py = target_row - 1
                c_py = 6
                if r_py < len(all_values) and c_py < len(all_values[r_py]):
                    current_note = str(all_values[r_py][c_py]).strip()
                else:
                    current_note = ""
                    
            if current_note:
                parts = [p.strip() for p in current_note.split(',')]
                if formatted_note in parts:
                    parts.remove(formatted_note)
                new_note = ", ".join(parts) if parts else ""
            else:
                new_note = ""
                
            cell_updates[(target_row, 7)] = new_note
            
    if cell_updates:
        data_to_update = []
        for (r, c), val in cell_updates.items():
            data_to_update.append({
                "range": f"{col_num_to_letter(c)}{r}",
                "values": [[val]]
            })
        worksheet.batch_update(data_to_update)
        
    return len(cell_updates), errors
