import os
import sys
from collections.abc import Iterable
from typing import Any

current_dir = os.path.dirname(__file__)
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from instructor_service.database import get_connection
from payroll_engine.calculator import calculate_class_pay


def _summarize_rows(rows: Iterable[tuple[Any, ...]], base_rate_index: int) -> dict[str, float | int]:
    summary: dict[str, float | int] = {
        "total_classes": 0,
        "total_students": 0,
        "total_penalty": 0,
        "total_payroll": 0.0,
        "ca_x": 0,
        "ca_07x": 0,
        "ca_05x": 0,
    }

    for row in rows:
        base_rate = int(row[base_rate_index] or 0)
        student_count = int(row[base_rate_index + 1] or 0)
        penalty_fee = int(row[base_rate_index + 2] or 0)
        note = str(row[base_rate_index + 3] or "")
        pay = calculate_class_pay(base_rate, student_count, penalty_fee, note)

        summary["total_classes"] = int(summary["total_classes"]) + 1
        summary["total_students"] = int(summary["total_students"]) + student_count
        summary["total_penalty"] = int(summary["total_penalty"]) + penalty_fee
        summary["total_payroll"] = float(summary["total_payroll"]) + pay["gross_salary"]

        if pay["mark"] == "X":
            summary["ca_x"] = int(summary["ca_x"]) + 1
        elif pay["mark"] == "0.7X":
            summary["ca_07x"] = int(summary["ca_07x"]) + 1
        elif pay["mark"] == "0.5X":
            summary["ca_05x"] = int(summary["ca_05x"]) + 1

    summary["total_payroll"] = float(summary["total_payroll"]) - int(summary["total_penalty"])
    return summary


def generate_monthly_report(month: int, year: int) -> str:
    conn = get_connection()
    cursor = conn.cursor()
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
            return f"**BAO CAO THANG {month}/{year}**\n\nKhong co du lieu ca day nao."

        summary = _summarize_rows(rows, base_rate_index=1)
        total_classes = int(summary["total_classes"])
        total_students = int(summary["total_students"])
        avg_students = total_students / total_classes if total_classes else 0

        return (
            f"**BAO CAO TONG QUAN THANG {month}/{year}**\n\n"
            f"**TONG QUY LUONG DU KIEN:** `{int(summary['total_payroll']):,} d`\n\n"
            f"**Chi so hoat dong:**\n"
            f"- Tong so ca da day: {total_classes} ca\n"
            f"- Tong so luot HV: {total_students} luot\n"
            f"- Trung binh HV/ca: {avg_students:.1f}\n\n"
            f"**Phan loai ca day:**\n"
            f"- So ca X: {summary['ca_x']} ca\n"
            f"- So ca 0.7X: {summary['ca_07x']} ca\n"
            f"- So ca 0.5X: {summary['ca_05x']} ca\n\n"
            f"**Tong phat:** `{int(summary['total_penalty']):,} d`"
        )
    except Exception as exc:
        print(f"generate_monthly_report error: {exc}")
        return f"Loi truy xuat du lieu: {exc}"
    finally:
        cursor.close()
        conn.close()


def generate_check_report(month: int, year: int, query_str: str) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    query_upper = query_str.upper().strip()
    query = """
        SELECT i.id, i.name, i.department, i.group_name, i.base_rate,
               t.student_count, t.penalty_fee, t.note
        FROM teaching_logs t
        JOIN instructors i ON t.instructor_id = i.id
        WHERE EXTRACT(MONTH FROM t.date) = %s AND EXTRACT(YEAR FROM t.date) = %s
        AND (
            UPPER(i.id) = %s OR UPPER(i.group_name) = %s
            OR UPPER(i.department) = %s OR UPPER(i.name) LIKE %s
        )
    """

    try:
        cursor.execute(query, (month, year, query_upper, query_upper, query_upper, f"%{query_upper}%"))
        rows = cursor.fetchall()
        if not rows:
            return f"Khong tim thay du lieu cham cong cho `{query_str}` trong thang {month}/{year}."

        summary = _summarize_rows(rows, base_rate_index=4)
        return (
            f"**KET QUA TRA CUU: `{query_str}` (Thang {month}/{year})**\n\n"
            f"**Tong luong:** `{int(summary['total_payroll']):,} d`\n\n"
            f"**Chi tiet ca day:**\n"
            f"- Tong so ca: {summary['total_classes']} ca\n"
            f"- So ca X: {summary['ca_x']} ca\n"
            f"- So ca 0.7X: {summary['ca_07x']} ca\n"
            f"- So ca 0.5X: {summary['ca_05x']} ca\n"
            f"- Luot HV: {summary['total_students']} luot\n\n"
            f"**Phat vi pham:** `{int(summary['total_penalty']):,} d`"
        )
    except Exception as exc:
        print(f"generate_check_report error: {exc}")
        return f"Loi truy xuat du lieu: {exc}"
    finally:
        cursor.close()
        conn.close()
