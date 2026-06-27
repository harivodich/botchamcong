from fastapi import FastAPI, HTTPException
from models import Instructor
import database

app = FastAPI(title="Instructor Management Service")

@app.on_event("startup")
def startup_event():
    database.init_db()

@app.get("/instructors")
def read_instructors():
    return database.get_all_instructors()

# API: Thêm giáo viên mới (Thay vì phải sửa code)
@app.post("/instructors")
def create_instructor(instructor: Instructor):
    success = database.add_instructor(instructor)
    if not success:
        raise HTTPException(status_code=400, detail="Mã Giáo viên này đã tồn tại!")
    return {"message": f"Đã thêm giáo viên {instructor.name} thành công."}

# API: Cập nhật giá ca dạy
@app.put("/instructors/{instructor_id}/rate")
def update_rate(instructor_id: str, new_rate: int):
    success = database.update_instructor_rate(instructor_id, new_rate)
    if not success:
        raise HTTPException(status_code=404, detail="Không tìm thấy Mã Giáo viên này.")
    return {"message": "Cập nhật đơn giá thành công."}