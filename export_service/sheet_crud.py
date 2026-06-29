import gspread
from export_service.sheet_manager import get_or_create_monthly_sheet, get_google_client, SPREADSHEET_ID

DEPARTMENTS = {"YOGA", "GX"}


def _normalize(value) -> str:
    return " ".join(str(value or "").casefold().split())


def _cell(row, index: int) -> str:
    return str(row[index]).strip() if len(row) > index else ""


def _is_instructor_row(row) -> bool:
    return bool(_cell(row, 1) and _cell(row, 2) and _cell(row, 3))


def _row_has_exact_value(row, expected: str, max_cols: int = 5) -> bool:
    expected_normalized = _normalize(expected)
    return any(_normalize(value) == expected_normalized for value in row[:max_cols])


def _is_department_header(row, department: str) -> bool:
    return not _is_instructor_row(row) and _row_has_exact_value(row, department)


def _is_any_department_header(row) -> bool:
    return any(_is_department_header(row, department) for department in DEPARTMENTS)


def _is_group_header(row, group_name: str) -> bool:
    return not _is_instructor_row(row) and _row_has_exact_value(row, group_name)


def _find_group_header_row(all_values, department: str, group_name: str) -> int:
    dept_row_index = None
    for index, row in enumerate(all_values):
        if _is_department_header(row, department):
            dept_row_index = index
            break

    if dept_row_index is None:
        raise ValueError(f"Khong tim thay bo phan '{department}' tren sheet.")

    for index in range(dept_row_index + 1, len(all_values)):
        row = all_values[index]
        if _is_any_department_header(row):
            break
        if _is_group_header(row, group_name):
            return index + 1

    raise ValueError(f"Khong tim thay nhom '{group_name}' trong bo phan '{department}' tren sheet.")


def get_template_and_current_sheet(month: int, year: int):
    gc = get_google_client()
    spreadsheet = gc.open_by_key(SPREADSHEET_ID or "")
    
    try:
        template_sheet = spreadsheet.worksheet("Template_Form")
    except gspread.exceptions.WorksheetNotFound:
        template_sheet = None
        
    current_sheet = get_or_create_monthly_sheet(month, year)
    
    return template_sheet, current_sheet

def _add_instructor_to_worksheet(worksheet, group_name: str, ins_data):
    all_values = worksheet.get_all_values()
    
    # 1. Tìm dòng tiêu đề của nhóm
    group_header_row = _find_group_header_row(all_values, ins_data.department, group_name)
        
    # Chèn vào ngay dưới giáo viên đầu tiên
    first_ins_row = group_header_row + 1
    insert_row_idx = first_ins_row + 1
    sheet_id = worksheet.id
    
    requests = [
        {
            "insertDimension": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": insert_row_idx - 1,
                    "endIndex": insert_row_idx
                },
                "inheritFromBefore": True
            }
        },
        {
            "copyPaste": {
                "source": {
                    "sheetId": sheet_id,
                    "startRowIndex": first_ins_row - 1,
                    "endRowIndex": first_ins_row,
                    "startColumnIndex": 0,
                    "endColumnIndex": 50
                },
                "destination": {
                    "sheetId": sheet_id,
                    "startRowIndex": insert_row_idx - 1,
                    "endRowIndex": insert_row_idx,
                    "startColumnIndex": 0,
                    "endColumnIndex": 50
                },
                "pasteType": "PASTE_NORMAL",
                "pasteOrientation": "NORMAL"
            }
        }
    ]
    
    worksheet.spreadsheet.batch_update({"requests": requests})
    
    # Lấy lại dữ liệu sau khi chèn để tính STT
    updated_values = worksheet.get_all_values()
    
    cells_to_update = [
        {"range": f"B{insert_row_idx}", "values": [[ins_data.id]]}, # Mã GV ở Cột B
        {"range": f"C{insert_row_idx}", "values": [[ins_data.name]]},
        {"range": f"D{insert_row_idx}", "values": [[ins_data.department]]},
        {"range": f"E{insert_row_idx}", "values": [[ins_data.title]]},
        {"range": f"F{insert_row_idx}", "values": [[""]]}, # Xóa tiền phạt
        {"range": f"G{insert_row_idx}", "values": [[""]]},  # Xóa ghi chú
        {"range": f"K{insert_row_idx}", "values": [[ins_data.base_rate]]} # Cập nhật Đơn giá
    ]
    
    # Xóa dữ liệu các ngày (cột P -> AT)
    clear_row_data = ["" for _ in range(31)]
    cells_to_update.append({"range": f"P{insert_row_idx}:AT{insert_row_idx}", "values": [clear_row_data]})
    
    # Tính lại STT
    current_row = group_header_row + 1
    count = 1
    stt_col_range = []
    
    while current_row <= len(updated_values):
        row_data = updated_values[current_row - 1]
        # Check cột Bộ phận để đếm, Cột D là index 3, dự phòng Cột C index 2
        dept = ""
        if len(row_data) > 3 and str(row_data[3]).strip():
            dept = str(row_data[3]).strip()
        elif len(row_data) > 2 and str(row_data[2]).strip():
            dept = str(row_data[2]).strip()
            
        if dept: # Có bộ phận nghĩa là dòng giáo viên
            stt_col_range.append([count])
            count += 1
            current_row += 1
        else:
            break
            
    if stt_col_range:
        cells_to_update.append({
            "range": f"A{group_header_row + 1}:A{group_header_row + len(stt_col_range)}",
            "values": stt_col_range
        })
        
    worksheet.batch_update(cells_to_update)

def add_instructor_to_sheets(month: int, year: int, group_name: str, ins_data):
    template_sheet, current_sheet = get_template_and_current_sheet(month, year)
    if template_sheet is not None:
        _add_instructor_to_worksheet(template_sheet, group_name, ins_data)
    if current_sheet is not None:
        _add_instructor_to_worksheet(current_sheet, group_name, ins_data)

def _delete_instructor_from_worksheet(worksheet, ins_name: str):
    all_values = worksheet.get_all_values()
    target_row_idx = -1
    for i, row in enumerate(all_values):
        # Tên GV ở Cột C (index 2) hoặc B (index 1)
        if len(row) > 2 and str(row[2]).strip().lower() == ins_name.strip().lower():
            target_row_idx = i + 1
            break
        elif len(row) > 1 and str(row[1]).strip().lower() == ins_name.strip().lower():
            target_row_idx = i + 1
            break
            
    if target_row_idx == -1:
        return # Bỏ qua nếu không tìm thấy
        
    worksheet.delete_rows(target_row_idx)
    
    # Tìm Header của nhóm để đánh lại STT
    group_header_row = target_row_idx - 1
    while group_header_row > 0:
        row_data = all_values[group_header_row - 1]
        dept = ""
        if len(row_data) > 3 and str(row_data[3]).strip():
            dept = str(row_data[3]).strip()
        elif len(row_data) > 2 and str(row_data[2]).strip():
            dept = str(row_data[2]).strip()
            
        if not dept:
            break
        group_header_row -= 1
        
    updated_values = worksheet.get_all_values()
    current_row = group_header_row + 1
    count = 1
    stt_col_range = []
    while current_row <= len(updated_values):
        row_data = updated_values[current_row - 1]
        dept = ""
        if len(row_data) > 3 and str(row_data[3]).strip():
            dept = str(row_data[3]).strip()
        elif len(row_data) > 2 and str(row_data[2]).strip():
            dept = str(row_data[2]).strip()
            
        if dept:
            stt_col_range.append([count])
            count += 1
            current_row += 1
        else:
            break
            
    if stt_col_range:
        worksheet.batch_update([{
            "range": f"A{group_header_row + 1}:A{group_header_row + len(stt_col_range)}",
            "values": stt_col_range
        }])

def delete_instructor_from_sheets(month: int, year: int, ins_name: str):
    template_sheet, current_sheet = get_template_and_current_sheet(month, year)
    if template_sheet is not None:
        _delete_instructor_from_worksheet(template_sheet, ins_name)
    if current_sheet is not None:
        _delete_instructor_from_worksheet(current_sheet, ins_name)

def _update_instructor_on_worksheet(worksheet, old_name: str, ins_data):
    all_values = worksheet.get_all_values()
    target_row_idx = -1
    for i, row in enumerate(all_values):
        if len(row) > 2 and str(row[2]).strip().lower() == old_name.strip().lower():
            target_row_idx = i + 1
            break
        elif len(row) > 1 and str(row[1]).strip().lower() == old_name.strip().lower():
            target_row_idx = i + 1
            break
            
    if target_row_idx == -1:
        return
        
    cells_to_update = [
        {"range": f"B{target_row_idx}", "values": [[ins_data.id]]},
        {"range": f"C{target_row_idx}", "values": [[ins_data.name]]},
        {"range": f"D{target_row_idx}", "values": [[ins_data.department]]},
        {"range": f"E{target_row_idx}", "values": [[ins_data.title]]},
        {"range": f"K{target_row_idx}", "values": [[ins_data.base_rate]]}
    ]
    worksheet.batch_update(cells_to_update)

def update_instructor_on_sheets(month: int, year: int, old_name: str, old_group_name: str, ins_data):
    template_sheet, current_sheet = get_template_and_current_sheet(month, year)
    
    # Nếu group name thay đổi, chúng ta cần xoá khỏi chỗ cũ và thêm lại vào chỗ mới
    if old_group_name.strip().upper() != ins_data.group_name.strip().upper():
        if template_sheet is not None:
            _delete_instructor_from_worksheet(template_sheet, old_name)
            _add_instructor_to_worksheet(template_sheet, ins_data.group_name, ins_data)
        if current_sheet is not None:
            _delete_instructor_from_worksheet(current_sheet, old_name)
            _add_instructor_to_worksheet(current_sheet, ins_data.group_name, ins_data)
    else:
        if template_sheet is not None:
            _update_instructor_on_worksheet(template_sheet, old_name, ins_data)
        if current_sheet is not None:
            _update_instructor_on_worksheet(current_sheet, old_name, ins_data)
