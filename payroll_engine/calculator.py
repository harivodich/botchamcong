from typing import Final, TypedDict


class ClassPay(TypedDict):
    mark: str
    base_value: float
    multiplier: float
    gross_salary: float
    net_salary: float


MARK_VALUES: Final[dict[str, float]] = {
    "X": 1.0,
    "0.7X": 0.7,
    "0.5X": 0.5,
}


def calculate_mark(student_count: int, note: str = "") -> tuple[str, float]:
    """
    Quy đổi số lượng học viên thành hệ số công cơ bản.
    Trả về Tuple: (Dấu công chuẩn, Hệ số nhân)
    - >= 5 học viên: 1 công ("X")
    - == 4 học viên: 0.7 công ("0.7X")
    - <= 3 học viên: 0.5 công ("0.5X")
    """
    if student_count >= 5:
        base_mark = "X"
    elif student_count == 4:
        base_mark = "0.7X"
    elif student_count > 0:
        base_mark = "0.5X"
    else:
        return "", 1.0 # Trường hợp 0 học viên hoặc lỗi
        
    # Xử lý hệ số linh hoạt bằng Regex (Ví dụ: x2, x1.5, x3, x2.5)
    import re
    multiplier = 1.0
    note_lower = note.lower()
    
    match = re.search(r'[x×]\s*(\d+(?:[\.,]\d+)?)', note_lower)
    if match:
        try:
            multiplier = float(match.group(1).replace(",", "."))
        except ValueError:
            pass
            
    return base_mark, multiplier


def calculate_class_pay(
    base_rate: int,
    student_count: int,
    penalty_fee: int = 0,
    note: str = "",
) -> ClassPay:
    mark, multiplier = calculate_mark(student_count, note)
    base_value = MARK_VALUES.get(mark, 0.0)
    gross_salary = float(base_rate * base_value * multiplier)

    return {
        "mark": mark,
        "base_value": base_value,
        "multiplier": multiplier,
        "gross_salary": gross_salary,
        "net_salary": gross_salary - penalty_fee,
    }


def calculate_sheet_penalty_fee(
    base_rate: int,
    student_count: int,
    penalty_fee: int = 0,
    note: str = "",
) -> int:
    pay = calculate_class_pay(base_rate, student_count, penalty_fee, note)
    base_salary = int(base_rate * pay["base_value"])
    bonus = max(0, int(pay["gross_salary"]) - base_salary)
    return penalty_fee - bonus
