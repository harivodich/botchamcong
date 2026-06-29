import os
import sys
from typing import Any

current_dir = os.path.dirname(__file__)
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from export_service.excel_writer import fill_instructor_works_batch
from ingestion_service.excel_parser import parse_weekly_timesheet
from instructor_service.database import add_teaching_log, get_instructor_by_name
from payroll_engine.calculator import calculate_class_pay, calculate_sheet_penalty_fee


def process_timesheet(input_filepath: str, file_hash: str | None = None) -> dict[str, Any]:
    print(f"Processing file: {input_filepath}")

    records = parse_weekly_timesheet(input_filepath)
    print(f"Parsed {len(records)} valid records.")

    errors: list[str] = []
    pending_logs: list[dict[str, Any]] = []
    works_by_month: dict[tuple[int, int], list[dict[str, Any]]] = {}

    for record in records:
        day = int(record["day"])
        month = int(record["month"])
        year = int(record["year"])
        instructor_name = str(record["instructor_name"]).strip()
        student_count = int(record["student_count"])
        penalty_fee = int(record.get("penalty_fee", 0) or 0)
        note = str(record.get("note", "") or "").strip()

        instructor = get_instructor_by_name(instructor_name)
        if not instructor:
            errors.append(
                f"Canh bao: Giao vien '{instructor_name}' chua co trong Database, "
                "bo qua ca day nay."
            )
            continue

        pay = calculate_class_pay(
            base_rate=int(instructor.get("base_rate", 0) or 0),
            student_count=student_count,
            penalty_fee=penalty_fee,
            note=note,
        )
        sheet_penalty_fee = calculate_sheet_penalty_fee(
            base_rate=int(instructor.get("base_rate", 0) or 0),
            student_count=student_count,
            penalty_fee=penalty_fee,
            note=note,
        )
        mark = pay["mark"]

        if not mark and not penalty_fee and not note:
            if student_count > 0:
                errors.append(
                    f"Ca day cua {instructor_name} ngay {day}/{month} "
                    f"co {student_count} HV, khong duoc tinh cong."
                )
            continue

        key = (month, year)
        works_by_month.setdefault(key, []).append(
            {
                "instructor_id": instructor["id"],
                "instructor_name": instructor_name,
                "day": day,
                "mark": mark,
                "penalty_fee": penalty_fee,
                "sheet_penalty_fee": sheet_penalty_fee,
                "note": note,
            }
        )
        pending_logs.append(
            {
                "date_str": f"{year}-{month:02d}-{day:02d}",
                "instructor_id": instructor["id"],
                "student_count": student_count,
                "penalty_fee": penalty_fee,
                "note": note,
            }
        )

        if not mark and student_count > 0:
            errors.append(
                f"Ca day cua {instructor_name} ngay {day}/{month} co {student_count} HV, "
                "khong du tinh cong nhung van luu phat/ghi chu."
            )

    success_count = 0
    sheet_failed = False
    for (month, year), works in works_by_month.items():
        try:
            _, sheet_errors = fill_instructor_works_batch(month, year, works)
        except Exception as exc:
            sheet_failed = True
            errors.append(f"Loi nghiem trong khi ghi du lieu thang {month}/{year}: {exc}")
            continue

        if sheet_errors:
            sheet_failed = True
            errors.extend(sheet_errors)
            continue

        success_count += len(works)

    # DB history is committed only after Sheets writes succeed, so reports/undo
    # cannot count rows that were never written to the operational sheet.
    if not sheet_failed:
        for log in pending_logs:
            add_teaching_log(
                log["date_str"],
                log["instructor_id"],
                log["student_count"],
                log["penalty_fee"],
                log["note"],
                file_hash,
            )

    print("Finished processing file.")
    print(f"Success: {success_count} classes.")
    print(f"Errors/warnings: {len(errors)}")

    return {
        "success": success_count,
        "errors": errors,
        "sheet_failed": sheet_failed,
        "processed_months": [
            {"month": month, "year": year}
            for month, year in sorted(works_by_month)
        ],
    }


if __name__ == "__main__":
    test_file = sys.argv[1] if len(sys.argv) > 1 else None
    if test_file and os.path.exists(test_file):
        process_timesheet(test_file)
    else:
        print("Please pass a timesheet file path.")
