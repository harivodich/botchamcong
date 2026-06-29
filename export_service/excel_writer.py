from collections.abc import Mapping
from datetime import date
from typing import Any

from payroll_engine.calculator import calculate_mark, calculate_sheet_penalty_fee
from instructor_service.database import get_connection

from .sheet_manager import get_or_create_monthly_sheet, _worksheet_is_locked


def col_num_to_letter(n: int) -> str:
    value = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        value = chr(65 + remainder) + value
    return value


def _parse_int(value: Any) -> int:
    text = str(value or "0").replace(".", "").replace(",", "").strip()
    return int(text) if text.lstrip("-").isdigit() else 0


def _build_row_maps(all_values: list[list[str]]) -> tuple[dict[str, int], dict[str, int]]:
    id_to_row: dict[str, int] = {}
    name_counts: dict[str, int] = {}

    for row_data in all_values[5:]:
        if len(row_data) > 2:
            name = str(row_data[2]).strip().lower()
            if name:
                name_counts[name] = name_counts.get(name, 0) + 1

    name_seen: dict[str, int] = {}
    name_to_row: dict[str, int] = {}
    for row_idx, row_data in enumerate(all_values, start=1):
        if row_idx <= 5 or len(row_data) <= 2:
            continue

        instructor_id = str(row_data[1]).strip().upper() if len(row_data) > 1 else ""
        if instructor_id:
            id_to_row[instructor_id] = row_idx

        name = str(row_data[2]).strip().lower()
        if not name:
            continue

        if name_counts.get(name, 0) > 1:
            name_seen[name] = name_seen.get(name, 0) + 1
            name_to_row[f"{name} {name_seen[name]}"] = row_idx
        else:
            name_to_row[name] = row_idx

    return id_to_row, name_to_row


def _find_target_row(
    work: Mapping[str, Any],
    id_to_row: Mapping[str, int],
    name_to_row: Mapping[str, int],
) -> int | None:
    instructor_id = str(work.get("instructor_id", "")).strip().upper()
    if instructor_id and instructor_id in id_to_row:
        return id_to_row[instructor_id]

    instructor_name = str(work.get("instructor_name", "")).strip().lower()
    return name_to_row.get(instructor_name)


def _current_cell_value(
    all_values: list[list[str]],
    cell_updates: Mapping[tuple[int, int], Any],
    row: int,
    col: int,
) -> str:
    if (row, col) in cell_updates:
        return str(cell_updates[(row, col)]).strip()

    r_idx = row - 1
    c_idx = col - 1
    if r_idx < len(all_values) and c_idx < len(all_values[r_idx]):
        return str(all_values[r_idx][c_idx]).strip()
    return ""


def _append_mark(current_value: str, mark: str) -> str:
    if not current_value:
        return mark
    if mark == "X" and current_value == "X":
        return "XX"
    if mark == "X" and current_value == "XX":
        return "XXX"
    return f"{current_value}, {mark}"


def _remove_mark(current_value: str, mark: str) -> str:
    if not current_value:
        return ""
    if mark == "X" and current_value == "XXX":
        return "XX"
    if mark == "X" and current_value == "XX":
        return "X"
    if mark == "X" and current_value == "X":
        return ""

    parts = [part.strip() for part in current_value.split(",")]
    if mark in parts:
        parts.remove(mark)
    return ", ".join(parts)


def _append_note(current_note: str, day: int, note: str) -> str:
    formatted_note = f"Ngay {day}: {note}"
    return f"{current_note}, {formatted_note}" if current_note else formatted_note


def _remove_note(current_note: str, day: int, note: str) -> str:
    formatted_note = f"Ngay {day}: {note}"
    parts = [part.strip() for part in current_note.split(",")]
    if formatted_note in parts:
        parts.remove(formatted_note)
    return ", ".join(parts)


def _batch_update_cells(worksheet: Any, cell_updates: Mapping[tuple[int, int], Any]) -> None:
    if not cell_updates:
        return

    worksheet.batch_update(
        [
            {"range": f"{col_num_to_letter(col)}{row}", "values": [[value]]}
            for (row, col), value in cell_updates.items()
        ]
    )


def fill_instructor_works_batch(month: int, year: int, works: list[dict[str, Any]]) -> tuple[int, list[str]]:
    if not works:
        return 0, []

    worksheet = get_or_create_monthly_sheet(month, year)
    if _worksheet_is_locked(worksheet.spreadsheet, worksheet):
        return 0, [f"Bảng lương Tháng {month}/{year} đã CHỐT SỔ. Hệ thống từ chối nhận thêm dữ liệu!"]
        
    all_values = worksheet.get_all_values()
    id_to_row, name_to_row = _build_row_maps(all_values)
    cell_updates: dict[tuple[int, int], Any] = {}
    errors: list[str] = []

    for work in works:
        target_row = _find_target_row(work, id_to_row, name_to_row)
        if not target_row:
            errors.append(f"Khong tim thay giao vien '{work.get('instructor_name', '')}' tren sheet.")
            continue

        day = int(work["day"])
        mark = str(work.get("mark", "") or "")
        penalty_fee = int(work.get("penalty_fee", 0) or 0)
        sheet_penalty_fee = int(work.get("sheet_penalty_fee", penalty_fee) or 0)
        note = str(work.get("note", "") or "").strip()

        if mark:
            target_col = 15 + day
            current_value = _current_cell_value(all_values, cell_updates, target_row, target_col)
            cell_updates[(target_row, target_col)] = _append_mark(current_value, mark)

        if sheet_penalty_fee:
            current_penalty = _parse_int(_current_cell_value(all_values, cell_updates, target_row, 6))
            cell_updates[(target_row, 6)] = current_penalty + sheet_penalty_fee

        if note:
            current_note = _current_cell_value(all_values, cell_updates, target_row, 7)
            cell_updates[(target_row, 7)] = _append_note(current_note, day, note)

    _batch_update_cells(worksheet, cell_updates)
    return len(cell_updates), errors


def rollback_instructor_works_batch(month: int, year: int, works: list[dict[str, Any]]) -> tuple[int, list[str]]:
    if not works:
        return 0, []

    worksheet = get_or_create_monthly_sheet(month, year)
    if _worksheet_is_locked(worksheet.spreadsheet, worksheet):
        return 0, [f"Bảng lương Tháng {month}/{year} đã CHỐT SỔ. Không thể thu hồi (undo) dữ liệu!"]
        
    all_values = worksheet.get_all_values()
    id_to_row, name_to_row = _build_row_maps(all_values)
    cell_updates: dict[tuple[int, int], Any] = {}
    errors: list[str] = []

    for work in works:
        target_row = _find_target_row(work, id_to_row, name_to_row)
        if not target_row:
            errors.append(f"Khong tim thay giao vien '{work.get('instructor_name', '')}' tren sheet.")
            continue

        log_date = work["date"]
        day = log_date.day if isinstance(log_date, date) else int(str(log_date).split("-")[-1])
        student_count = int(work["student_count"])
        penalty_fee = int(work.get("penalty_fee", 0) or 0)
        note = str(work.get("note", "") or "").strip()
        base_rate = int(work.get("base_rate", 0) or 0)
        sheet_penalty_fee = (
            calculate_sheet_penalty_fee(base_rate, student_count, penalty_fee, note)
            if base_rate
            else penalty_fee
        )
        mark, _ = calculate_mark(student_count, note)

        if mark:
            target_col = 15 + day
            current_value = _current_cell_value(all_values, cell_updates, target_row, target_col)
            cell_updates[(target_row, target_col)] = _remove_mark(current_value, mark)

        if sheet_penalty_fee:
            current_penalty = _parse_int(_current_cell_value(all_values, cell_updates, target_row, 6))
            cell_updates[(target_row, 6)] = current_penalty - sheet_penalty_fee

        if note:
            current_note = _current_cell_value(all_values, cell_updates, target_row, 7)
            cell_updates[(target_row, 7)] = _remove_note(current_note, day, note)

    _batch_update_cells(worksheet, cell_updates)
    return len(cell_updates), errors


def sync_bonus_adjustments_from_db(month: int, year: int) -> tuple[int, list[str]]:
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        SELECT i.id, i.name, i.base_rate, t.student_count, t.penalty_fee, t.note
        FROM teaching_logs t
        JOIN instructors i ON t.instructor_id = i.id
        WHERE EXTRACT(MONTH FROM t.date) = %s AND EXTRACT(YEAR FROM t.date) = %s
    """

    try:
        cursor.execute(query, (month, year))
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    if not rows:
        return 0, []

    worksheet = get_or_create_monthly_sheet(month, year)
    all_values = worksheet.get_all_values()
    id_to_row, name_to_row = _build_row_maps(all_values)
    target_penalties: dict[int, int] = {}
    errors: list[str] = []

    for ins_id, name, base_rate, student_count, penalty_fee, note in rows:
        work = {"instructor_id": ins_id, "instructor_name": name}
        target_row = _find_target_row(work, id_to_row, name_to_row)
        if not target_row:
            errors.append(f"Khong tim thay giao vien '{name}' tren sheet.")
            continue

        target_penalties[target_row] = target_penalties.get(target_row, 0) + calculate_sheet_penalty_fee(
            int(base_rate or 0),
            int(student_count or 0),
            int(penalty_fee or 0),
            str(note or ""),
        )

    cell_updates = {
        (row, 6): penalty
        for row, penalty in target_penalties.items()
    }
    _batch_update_cells(worksheet, cell_updates)
    return len(cell_updates), errors
