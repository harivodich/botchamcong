import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

# Cấu hình Supabase (từ .env)
load_dotenv(".env")
supa_host = os.getenv("DB_HOST")
supa_port = os.getenv("DB_PORT")
supa_name = os.getenv("DB_NAME")
supa_user = os.getenv("DB_USER")
supa_pass = os.getenv("DB_PASS")

# Cấu hình Local
local_host = "localhost"
local_port = "5432"
local_name = "gym_payroll"
local_user = "postgres"
local_pass = "123456"

try:
    print("Đang kết nối tới DB Local...")
    conn_local = psycopg2.connect(host=local_host, port=local_port, dbname=local_name, user=local_user, password=local_pass)
    cur_local = conn_local.cursor(cursor_factory=RealDictCursor)
    
    print("Đang khởi tạo cấu trúc bảng trên Supabase (nếu chưa có)...")
    import sys
    sys.path.append(os.path.dirname(__file__))
    from instructor_service.database import init_db
    init_db()

    print("Đang kết nối tới Supabase để copy...")
    conn_supa = psycopg2.connect(host=supa_host, port=supa_port, dbname=supa_name, user=supa_user, password=supa_pass)
    cur_supa = conn_supa.cursor()

    tables = ["instructors", "teaching_logs", "processed_files", "audit_logs"]

    for table in tables:
        print(f"Đang copy bảng {table}...")
        cur_local.execute(f"SELECT * FROM {table}")
        rows = cur_local.fetchall()
        
        if not rows:
            print(f"Bảng {table} trống.")
            continue
            
        # Lấy tên cột
        cols = rows[0].keys()
        col_names = ", ".join(cols)
        placeholders = ", ".join(["%s"] * len(cols))
        
        # Xóa dữ liệu cũ trên Supabase để tránh trùng lặp
        cur_supa.execute(f"DELETE FROM {table}")
        
        # Insert dữ liệu mới
        insert_query = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"
        for row in rows:
            values = tuple(row[col] for col in cols)
            cur_supa.execute(insert_query, values)
            
        print(f"Đã copy {len(rows)} dòng vào bảng {table}.")

    # Reset sequences (nếu có cột SERIAL)
    cur_supa.execute("SELECT setval('teaching_logs_id_seq', (SELECT MAX(id) FROM teaching_logs))")
    cur_supa.execute("SELECT setval('audit_logs_id_seq', (SELECT COALESCE(MAX(id), 1) FROM audit_logs))")

    conn_supa.commit()
    print("✅ MIGRATION THÀNH CÔNG!")
    
except Exception as e:
    print(f"❌ Lỗi: {e}")
finally:
    if 'conn_local' in locals(): conn_local.close()
    if 'conn_supa' in locals(): conn_supa.close()
