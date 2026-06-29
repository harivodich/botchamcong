import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import os
from dotenv import load_dotenv

# Đọc cấu hình từ file .env
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "gym_payroll")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "123456")

def create_database_if_not_exists():
    """
    Kết nối vào database mặc định (postgres) để kiểm tra và tạo DB 'gym_payroll' nếu chưa có.
    """
    try:
        # Kết nối tạm vào database 'postgres' mặc định
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname="postgres",
            user=DB_USER,
            password=DB_PASS
        )
        # Bắt buộc phải set autocommit để chạy lệnh CREATE DATABASE
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Kiểm tra xem database đã tồn tại chưa
        cursor.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s", (DB_NAME,))
        exists = cursor.fetchone()
        
        if not exists:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB_NAME)))
            print(f"Đã tạo Database '{DB_NAME}' thành công!")
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Lỗi khi kiểm tra/tạo database: {e}")

def get_connection():
    """
    Kết nối vào Supabase PostgreSQL
    Sử dụng options để set schema mặc định là public (tránh lỗi với PgBouncer Transaction Mode)
    """
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        options="-c search_path=public"
    )

def init_db():
    # 1. Tạo database trước
    create_database_if_not_exists()
    
    # 2. Kết nối vào DB vừa tạo và tạo bảng
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Tạo bảng instructors (Danh mục giáo viên)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS instructors (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                department VARCHAR(50) NOT NULL,
                group_name VARCHAR(100) NOT NULL,
                title VARCHAR(100),
                base_rate INTEGER NOT NULL
            )
        ''')
        
        # Thêm bảng processed_files
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_files (
                file_hash VARCHAR(64) PRIMARY KEY,
                file_name VARCHAR(255),
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tạo bảng teaching_logs (Lịch sử các ca dạy thực tế)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS teaching_logs (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL,
                instructor_id VARCHAR(50) REFERENCES instructors(id) ON DELETE CASCADE,
                student_count INTEGER NOT NULL,
                penalty_fee INTEGER DEFAULT 0,
                note TEXT,
                file_hash VARCHAR(64),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tạo bảng audit_logs (Lưu vết thao tác người dùng)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_id BIGINT NOT NULL,
                username VARCHAR(100),
                action VARCHAR(50) NOT NULL,
                details TEXT
            )
        ''')
        
        # Thêm cột file_hash cho DB cũ (nếu chưa có)
        conn.commit()
        try:
            cursor.execute("ALTER TABLE teaching_logs ADD COLUMN file_hash VARCHAR(64)")
        except psycopg2.Error:
            conn.rollback() # Bỏ qua nếu cột đã tồn tại
        
        
        # Thêm dữ liệu mẫu nếu bảng instructors trống
        cursor.execute("SELECT COUNT(*) FROM instructors")
        if cursor.fetchone()[0] == 0:
            sample_data = [
                ("GV01", "Vikram", "YOGA", "HẰNG TRẦN 0912762702", "MASTER", 330000),
                ("GV02", "MAAN", "YOGA", "FREELANCE", "MASTER", 300000),
                ("GV03", "Sơn Tùng", "GX", "FREELANCE", "DANSPORT", 300000),
                ("GV04", "SHAN", "GX", "HẰNG TRẦN 0912762702", "", 300000)
            ]
            cursor.executemany("INSERT INTO instructors (id, name, department, group_name, title, base_rate) VALUES (%s, %s, %s, %s, %s, %s)", sample_data)
        
        conn.commit()
        cursor.close()
        conn.close()
        print("Đã khởi tạo bảng và dữ liệu mẫu thành công!")
    except Exception as e:
        print(f"Lỗi khi khởi tạo bảng: {e}")

def get_all_instructors():
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM instructors")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def add_instructor(instructor_data):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO instructors (id, name, department, group_name, title, base_rate) VALUES (%s, %s, %s, %s, %s, %s)",
            (instructor_data.id, instructor_data.name, instructor_data.department, instructor_data.group_name, instructor_data.title, instructor_data.base_rate)
        )
        conn.commit()
        return True
    except psycopg2.IntegrityError:
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

def update_instructor_rate(instructor_id: str, new_rate: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE instructors SET base_rate = %s WHERE id = %s", (new_rate, instructor_id))
    conn.commit()
    row_count = cursor.rowcount
    cursor.close()
    conn.close()
    return row_count > 0

def get_instructor_by_name(name: str):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    # Tìm kiếm không phân biệt chữ hoa chữ thường
    cursor.execute("SELECT * FROM instructors WHERE LOWER(name) = LOWER(%s) LIMIT 1", (name.strip(),))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row

def get_instructor_by_id(ins_id: str):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM instructors WHERE id = %s LIMIT 1", (ins_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row

def update_instructor_details(ins_id: str, name: str, department: str, group_name: str, title: str, base_rate: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE instructors 
        SET name = %s, department = %s, group_name = %s, title = %s, base_rate = %s 
        WHERE id = %s
    """, (name, department, group_name, title, base_rate, ins_id))
    conn.commit()
    row_count = cursor.rowcount
    cursor.close()
    conn.close()
    return row_count > 0

def delete_instructor(ins_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM instructors WHERE id = %s", (ins_id,))
    conn.commit()
    row_count = cursor.rowcount
    cursor.close()
    conn.close()
    return row_count > 0

def add_teaching_log(date_str: str, instructor_id: str, student_count: int, penalty_fee: int, note: str, file_hash: str | None = None):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO teaching_logs (date, instructor_id, student_count, penalty_fee, note, file_hash) 
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (date_str, instructor_id, student_count, penalty_fee, note, file_hash)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Lỗi khi lưu teaching_log: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

def is_file_processed(file_hash: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM processed_files WHERE file_hash = %s", (file_hash,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row is not None

def record_processed_file(file_hash: str, file_name: str):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO processed_files (file_hash, file_name) VALUES (%s, %s)", (file_hash, file_name))
        conn.commit()
    except Exception as e:
        print(f"Lỗi ghi nhận file processed: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def get_full_hash(short_hash: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT file_hash FROM processed_files WHERE file_hash LIKE %s", (short_hash + '%',))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if row:
        return row[0]
    return None

def get_logs_by_file_hash(file_hash: str):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT tl.date, tl.instructor_id, i.name as instructor_name, i.base_rate, tl.student_count, tl.penalty_fee, tl.note
        FROM teaching_logs tl
        JOIN instructors i ON tl.instructor_id = i.id
        WHERE tl.file_hash = %s
    """, (file_hash,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def delete_logs_by_file_hash(file_hash: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM teaching_logs WHERE file_hash = %s", (file_hash,))
    conn.commit()
    row_count = cursor.rowcount
    cursor.close()
    conn.close()
    return row_count > 0

def remove_processed_file(file_hash: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM processed_files WHERE file_hash = %s", (file_hash,))
    conn.commit()
    cursor.close()
    conn.close()

def add_audit_log(user_id: int, username: str, action: str, details: str):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO audit_logs (user_id, username, action, details) 
               VALUES (%s, %s, %s, %s)""",
            (user_id, username, action, details)
        )
        conn.commit()
    except Exception as e:
        print(f"Lỗi ghi log: {e}")
    finally:
        cursor.close()
        conn.close()
