import os
import subprocess
from datetime import datetime
from dotenv import load_dotenv

# Đọc cấu hình từ file .env
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "gym_payroll")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "123456")

BACKUP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backups"))

def run_backup():
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"backup_{DB_NAME}_{timestamp}.sql")
    
    # Thiết lập biến môi trường chứa password cho pg_dump
    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASS
    
    # Câu lệnh pg_dump
    cmd = [
        "pg_dump",
        "-h", str(DB_HOST),
        "-p", str(DB_PORT),
        "-U", str(DB_USER),
        "-d", str(DB_NAME),
        "-f", backup_file
    ]
    
    try:
        print(f"Đang tiến hành sao lưu database vào: {backup_file} ...")
        # Run process
        result = subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
        print("✅ Sao lưu Database thành công!")
        return backup_file
    except subprocess.CalledProcessError as e:
        print(f"❌ Lỗi sao lưu Database: {e.stderr}")
        return None
    except FileNotFoundError:
        print("❌ Lỗi: Không tìm thấy lệnh 'pg_dump'. Vui lòng thêm thư mục bin của PostgreSQL vào biến môi trường PATH của Windows.")
        return None

if __name__ == "__main__":
    run_backup()
