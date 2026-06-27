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
    
    match = re.search(r'x(\d+(?:\.\d+)?)', note_lower)
    if match:
        try:
            multiplier = float(match.group(1))
        except ValueError:
            pass
            
    return base_mark, multiplier
