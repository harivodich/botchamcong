import gspread
import os
from dotenv import load_dotenv

current_dir = os.path.dirname(__file__)
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
load_dotenv(os.path.join(parent_dir, ".env"))

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
CREDENTIALS_PATH = os.path.join(parent_dir, "credentials.json")

def get_google_client():
    if not os.path.exists(CREDENTIALS_PATH):
        raise FileNotFoundError("Không tìm thấy file credentials.json! Vui lòng đặt nó ở thư mục gốc của project.")
    # Xác thực bằng service account
    gc = gspread.service_account(filename=CREDENTIALS_PATH)
    return gc

def get_or_create_monthly_sheet(month: int, year: int):
    """
    Kết nối vào Google Sheets.
    Kiểm tra xem sheet của tháng hiện tại đã có chưa.
    Nếu chưa, duplicate sheet 'Template' và đổi tên, cập nhật ô A3.
    Trả về object Worksheet.
    """
    if not SPREADSHEET_ID or SPREADSHEET_ID == "nhap_id_file_google_sheets_vao_day":
        raise ValueError("Chưa cấu hình SPREADSHEET_ID trong file .env!")
        
    gc = get_google_client()
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)
    
    sheet_name = f"Thang_{month:02d}_{year}"
    
    # Kiểm tra xem sheet đã tồn tại chưa
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        return worksheet
    except gspread.exceptions.WorksheetNotFound:
        # Nếu chưa tồn tại, tìm sheet 'Template_Form' để duplicate
        try:
            template_sheet = spreadsheet.worksheet("Template_Form")
        except gspread.exceptions.WorksheetNotFound:
            raise Exception("File Google Sheets của bạn PHẢI có một sheet tên là 'Template_Form' để làm mẫu nhân bản!")
            
        # Duplicate sheet
        worksheet = spreadsheet.duplicate_sheet(
            template_sheet.id,
            new_sheet_name=sheet_name
        )
        
        # Cập nhật ô A3
        worksheet.update_acell("A3", f"Tháng {month:02d} năm {year}")
        
        return worksheet

def lock_worksheet(month: int, year: int) -> bool:
    try:
        if not SPREADSHEET_ID or SPREADSHEET_ID == "nhap_id_file_google_sheets_vao_day":
            return False
            
        gc = get_google_client()
        spreadsheet = gc.open_by_key(SPREADSHEET_ID)
        sheet_name = f"Thang_{month:02d}_{year}"
        
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            return False
            
        # Lấy client email của Service Account
        credentials = getattr(gc, "auth", getattr(getattr(gc, "http_client", None), "auth", None))
        service_email = getattr(credentials, "signer_email", getattr(credentials, "service_account_email", ""))
        
        # Gửi request bằng batchUpdate để lock sheet cho 1 user
        body = {
            "requests": [
                {
                    "addProtectedRange": {
                        "protectedRange": {
                            "range": {
                                "sheetId": worksheet.id
                            },
                            "description": f"Chốt lương tháng {month}/{year}",
                            "warningOnly": False,
                            "editors": {
                                "users": [service_email],
                                "domainUsersCanEdit": False
                            }
                        }
                    }
                }
            ]
        }
        
        spreadsheet.client.request(
            'post',
            f'https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}:batchUpdate',
            json=body
        )
        return True
    except Exception as e:
        print(f"Lỗi lock_worksheet: {e}")
        return False
