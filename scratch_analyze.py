import os
import sys
import pandas as pd

current_dir = os.path.dirname(__file__)
if current_dir not in sys.path:
    sys.path.append(current_dir)

from instructor_service.database import get_all_instructors
from payroll_engine.calculator import calculate_mark

def analyze_data():
    file_path = os.path.join(current_dir, "massive_test_v2.xlsx")
    if not os.path.exists(file_path):
        print("File massive_test_v2.xlsx không tồn tại!")
        return

    df = pd.read_excel(file_path)
    
    # Lấy thông tin lương từ DB
    instructors = get_all_instructors()
    rate_map = {ins["name"].strip().lower(): ins["base_rate"] for ins in instructors}
    
    total_x = 0
    total_0_7x = 0
    total_0_5x = 0
    total_penalty = 0
    total_money = 0
    
    ins_stats = {}
    
    for index, row in df.iterrows():
        name = str(row.iloc[1]).strip()
        if pd.isna(name) or name == 'nan' or name == '':
            continue
            
        lower_name = name.lower()
        base_rate = rate_map.get(lower_name, 0)
        
        student_count_val = row.iloc[2]
        try:
            student_count = int(student_count_val) if not pd.isna(student_count_val) else 0
        except:
            student_count = 0
            
        penalty_val = row.iloc[3]
        try:
            penalty = int(penalty_val) if not pd.isna(penalty_val) and str(penalty_val).strip() != "" else 0
        except:
            penalty = 0
            
        mark = calculate_mark(student_count)
        
        # Cập nhật thống kê
        if lower_name not in ins_stats:
            ins_stats[lower_name] = {
                "name": name,
                "x_count": 0,
                "0_7x_count": 0,
                "0_5x_count": 0,
                "penalty": 0,
                "money": 0,
                "base_rate": base_rate
            }
            
        stats = ins_stats[lower_name]
        stats["penalty"] += penalty
        total_penalty += penalty
        
        money_earned = 0
        if mark == "X":
            stats["x_count"] += 1
            total_x += 1
            money_earned = base_rate * 1.0
        elif mark == "0.7X":
            stats["0_7x_count"] += 1
            total_0_7x += 1
            money_earned = base_rate * 0.7
        elif mark == "0.5X":
            stats["0_5x_count"] += 1
            total_0_5x += 1
            money_earned = base_rate * 0.5
            
        stats["money"] += money_earned
        total_money += money_earned
        
    # Tính tổng tiền ròng (đã trừ phạt)
    total_net_money = total_money - total_penalty
    for s in ins_stats.values():
        s["net_money"] = s["money"] - s["penalty"]

    # Tạo báo cáo Markdown
    report = "# Báo cáo Thống kê Dữ liệu Chấm công\n\n"
    report += "## 1. Tổng quan toàn hệ thống\n"
    report += f"- **Tổng số ca X (>=5 HV):** {total_x} ca\n"
    report += f"- **Tổng số ca 0.7X (4 HV):** {total_0_7x} ca\n"
    report += f"- **Tổng số ca 0.5X (<=3 HV):** {total_0_5x} ca\n"
    report += f"- **Tổng tiền phạt:** {total_penalty:,.0f} VND\n"
    report += f"- **Tổng Lương Trái Tuyến (Chưa trừ phạt):** {total_money:,.0f} VND\n"
    report += f"- **Tổng Lương Thực Trả (Đã trừ phạt):** {total_net_money:,.0f} VND\n\n"
    
    report += "## 2. Chi tiết từng giáo viên\n\n"
    report += "| Tên Giáo Viên | Lương CB | Số ca X | Số ca 0.7X | Số ca 0.5X | Tiền Phạt | Lương Thực Trả |\n"
    report += "|---|---|---|---|---|---|---|\n"
    
    for lower_name, s in sorted(ins_stats.items(), key=lambda x: x[1]['net_money'], reverse=True):
        report += f"| {s['name']} | {s['base_rate']:,.0f} | {s['x_count']} | {s['0_7x_count']} | {s['0_5x_count']} | {s['penalty']:,.0f} | **{s['net_money']:,.0f}** |\n"
        
    report_path = os.path.join(current_dir, "analysis_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
        
    print(f"Báo cáo đã được tạo tại {report_path}")

if __name__ == "__main__":
    analyze_data()
