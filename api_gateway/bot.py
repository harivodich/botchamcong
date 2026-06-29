import asyncio
import os
import sys
import tempfile
from datetime import datetime
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, Document, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from dotenv import load_dotenv

# Đảm bảo có thể import các module từ thư mục bên ngoài
current_dir = os.path.dirname(__file__)
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from instructor_service.database import add_instructor, delete_instructor, update_instructor_details, get_instructor_by_id, get_all_instructors, add_audit_log
from instructor_service.models import Instructor
from payroll_engine.main import process_timesheet
from export_service.sheet_crud import add_instructor_to_sheets, delete_instructor_from_sheets, update_instructor_on_sheets

load_dotenv(os.path.join(parent_dir, ".env"))
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_IDS = os.getenv("ADMIN_IDS", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBAPP_HOST = os.getenv("WEBAPP_HOST", "0.0.0.0")
# Google Cloud Run tự động cấp biến môi trường PORT, ta phải đọc biến này
WEBAPP_PORT = int(os.getenv("PORT", os.getenv("WEBAPP_PORT", "8080")))

# Helper check quyền Admin
def is_admin(user_id: int) -> bool:
    if not ADMIN_IDS or ADMIN_IDS == "YOUR_TELEGRAM_ID_HERE":
        return False
    admin_list = [a.strip() for a in ADMIN_IDS.split(",") if a.strip()]
    return str(user_id) in admin_list

# Khởi tạo Bot và Dispatcher
bot = Bot(token=TOKEN) if TOKEN else None
dp = Dispatcher()

# --- FSM STATES ---
class AddGV(StatesGroup):
    ins_id = State()
    name = State()
    dept = State()
    group_name = State()
    title = State()
    rate = State()

class EditGV(StatesGroup):
    ins_id = State()
    name = State()
    dept = State()
    group_name = State()
    title = State()
    rate = State()

class DelGV(StatesGroup):
    ins_id = State()
    confirm = State()

class UndoFSM(StatesGroup):
    file_hash = State()

class CloseFSM(StatesGroup):
    month_year = State()

class ReportFSM(StatesGroup):
    month_year = State()

class CheckFSM(StatesGroup):
    month_year = State()
    query = State()

# --- GLOBAL HANDLERS ---
@dp.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is None:
        return
    await state.clear()
    await message.answer("✅ Đã hủy bỏ thao tác hiện tại.")

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    welcome_text = (
        "🤖 <b>Bot Tính Công Giáo Viên</b>\n\n"
        f"📊 <b>Bảng Lương Online:</b> <a href='https://docs.google.com/spreadsheets/d/{os.getenv('SPREADSHEET_ID')}/edit'>Bấm vào đây để xem</a>\n\n"
        "👇 <b>Chọn một chức năng bên dưới (Chỉ Admin):</b>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Báo cáo quỹ lương", callback_data="menu_report")],
        [InlineKeyboardButton(text="🔍 Tra cứu cá nhân", callback_data="menu_check")],
        [InlineKeyboardButton(text="🔒 Chốt lương (Xuất Excel)", callback_data="menu_close")],
        [InlineKeyboardButton(text="👨‍🏫 Thêm Giáo viên", callback_data="menu_add_gv"), 
         InlineKeyboardButton(text="📝 Sửa Giáo viên", callback_data="menu_edit_gv")],
        [InlineKeyboardButton(text="📋 Danh sách GV", callback_data="menu_list_gv"),
         InlineKeyboardButton(text="❌ Xóa Giáo viên", callback_data="menu_del_gv")],
        [InlineKeyboardButton(text="⏪ Thu hồi file lỗi", callback_data="menu_undo")]
    ])
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("menu_"))
async def process_menu_callback(callback: CallbackQuery, state: FSMContext):
    import logging
    logging.error(f"DEBUG: callback triggered with data {callback.data}")
    try:
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ Bạn không có quyền!", show_alert=True)
            return
            
        await callback.answer()
        action = callback.data.split("_", 1)[1]
        logging.error(f"DEBUG: action {action}")
        
        chat_id = callback.message.chat.id
        
        if action == "report":
            await state.set_state(ReportFSM.month_year)
            now = datetime.now()
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"Tháng Hiện Tại ({now.month}/{now.year})", callback_data=f"report_month_{now.month}_{now.year}")],
                [InlineKeyboardButton(text="Tháng Trước", callback_data=f"report_month_{now.month-1 if now.month>1 else 12}_{now.year if now.month>1 else now.year-1}")]
            ])
            await bot.send_message(chat_id, "👉 Chọn hoặc Nhập Tháng và Năm cần xuất Báo cáo (VD: `06/2026`):", reply_markup=kb)
            
        elif action == "check":
            await state.set_state(CheckFSM.month_year)
            now = datetime.now()
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"Tháng Hiện Tại ({now.month}/{now.year})", callback_data=f"check_month_{now.month}_{now.year}")],
                [InlineKeyboardButton(text="Tháng Trước", callback_data=f"check_month_{now.month-1 if now.month>1 else 12}_{now.year if now.month>1 else now.year-1}")]
            ])
            await bot.send_message(chat_id, "👉 Chọn hoặc Nhập Tháng và Năm cần tra cứu (VD: `06/2026`):", reply_markup=kb)
            
        elif action == "close":
            await state.set_state(CloseFSM.month_year)
            now = datetime.now()
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"Tháng Hiện Tại ({now.month}/{now.year})", callback_data=f"close_month_{now.month}_{now.year}")],
                [InlineKeyboardButton(text="Tháng Trước", callback_data=f"close_month_{now.month-1 if now.month>1 else 12}_{now.year if now.month>1 else now.year-1}")]
            ])
            await bot.send_message(chat_id, "👉 Chọn hoặc Nhập Tháng và Năm cần CHỐT LƯƠNG (VD: `06/2026`):", reply_markup=kb)
            
        elif action == "add_gv":
            await state.set_state(AddGV.ins_id)
            await bot.send_message(chat_id, "Bắt đầu thêm GV mới. Bạn có thể gõ /cancel để hủy bất kỳ lúc nào.\n\n👉 1. Vui lòng nhập Mã Giáo Viên (VD: GV05):")
            
        elif action == "edit_gv":
            await state.set_state(EditGV.ins_id)
            await bot.send_message(chat_id, "Bắt đầu sửa thông tin GV. Gõ /cancel để hủy.\n\n👉 Nhập Mã Giáo Viên cần sửa (VD: GV05):")
            
        elif action == "del_gv":
            await state.set_state(DelGV.ins_id)
            await bot.send_message(chat_id, "Bắt đầu XÓA Giáo Viên. Gõ /cancel để hủy.\n\n👉 Nhập Mã Giáo Viên cần xóa (VD: GV05):")
            
        elif action == "list_gv":
            instructors = get_all_instructors()
            if not instructors:
                await bot.send_message(chat_id, "Danh sách giáo viên hiện đang trống.")
                return
            report = "📋 DANH SÁCH GIÁO VIÊN\n\n"
            for ins in instructors:
                line = f"▪️ {ins['id']} - {ins['name']} ({ins['department']} - {ins['group_name']})\n"
                title_str = f"Chức danh: {ins['title']}, " if ins['title'] else ""
                line += f"   {title_str}Giá: {ins['base_rate']:,}đ\n"
                if len(report) + len(line) > 3500:
                    await bot.send_message(chat_id, report)
                    report = ""
                report += line
            if report:
                await bot.send_message(chat_id, report)
            
        elif action == "undo":
            await state.set_state(UndoFSM.file_hash)
            await bot.send_message(chat_id, "👉 Nhập Mã File (8 ký tự) bạn muốn thu hồi dữ liệu (hoặc gõ /cancel để hủy):")
    except Exception as e:
        logging.error(f"DEBUG: Exception in menu callback: {e}", exc_info=True)
        await bot.send_message(callback.message.chat.id if callback.message else callback.from_user.id, f"❌ Có lỗi xảy ra trong bot: {e}")

@dp.callback_query(F.data.startswith("report_month_") | F.data.startswith("check_month_") | F.data.startswith("close_month_"))
async def process_month_callback(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        parts = callback.data.split("_")
        action = parts[0]
        month, year = int(parts[2]), int(parts[3])
        msg = callback.message
        
        if action == "report":
            await state.clear()
            from payroll_engine.report import generate_monthly_report
            report_text = await asyncio.to_thread(generate_monthly_report, month, year)
            await msg.answer(report_text, parse_mode="Markdown")
            
        elif action == "check":
            await state.update_data(month=month, year=year)
            await state.set_state(CheckFSM.query)
            await msg.answer("👉 Nhập Mã GV (VD: GV05) hoặc Tên Nhóm (VD: YOGA) để tra cứu:")
            
        elif action == "close":
            await state.clear()
            status_msg = await msg.answer(f"⏳ Đang khóa bảng công Tháng {month}/{year} trên Google Sheets...")
            from export_service.excel_writer import sync_bonus_adjustments_from_db
            await asyncio.to_thread(sync_bonus_adjustments_from_db, month, year)
            from export_service.sheet_manager import lock_worksheet
            success = await asyncio.to_thread(lock_worksheet, month, year)
            
            if success:
                add_audit_log(callback.from_user.id, callback.from_user.username or "", "CLOSE_SHEET", f"Khóa lương tháng {month}/{year}")
                
                # XUẤT EXCEL
                from export_service.excel_generator import generate_payroll_excel
                excel_path = await asyncio.to_thread(generate_payroll_excel, month, year)
                
                await bot.edit_message_text(f"✅ Đã khóa thành công bảng lương Tháng {month}/{year} trên Google Sheets!", chat_id=msg.chat.id, message_id=status_msg.message_id)
                
                if excel_path and os.path.exists(excel_path):
                    from aiogram.types import FSInputFile
                    excel_file = FSInputFile(excel_path, filename=f"Bang_Luong_T{month}_{year}.xlsx")
                    await msg.answer_document(document=excel_file, caption=f"📊 File Bảng Lương Tổng hợp Tháng {month}/{year} (Đã chốt)")
            else:
                await bot.edit_message_text("❌ Có lỗi xảy ra khi gọi Google Sheets API để khóa.", chat_id=msg.chat.id, message_id=status_msg.message_id)
    except Exception as e:
        import logging
        logging.error(f"DEBUG: Exception in process_month_callback: {e}", exc_info=True)
        await bot.send_message(callback.message.chat.id if callback.message else callback.from_user.id, f"❌ Có lỗi xảy ra trong bot: {e}")

@dp.callback_query(F.data.startswith("dept_"))
async def process_dept_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    dept = callback.data.split("_")[1]
    msg = callback.message
    
    # We must know if we are in AddGV or EditGV FSM
    current_state = await state.get_state()
    if current_state == AddGV.dept.state:
        await state.update_data(dept=dept)
        await state.set_state(AddGV.group_name)
        await msg.answer(f"✅ Đã chọn bộ phận: {dept}\n\n👉 4. Nhập Tên Nhóm/Phân loại (VD: FREELANCE, HẰNG TRẦN...):")
    elif current_state == EditGV.dept.state:
        await state.update_data(dept=dept)
        await state.set_state(EditGV.group_name)
        data = await state.get_data()
        await msg.answer(f"✅ Đã chọn bộ phận: {dept}\n\n👉 Nhập Nhóm MỚI (Gửi `-` để giữ nguyên `{data['old_ins']['group_name']}`):")

# --- ADD_GV FSM ---
@dp.message(Command("add_gv"))
async def add_gv_start(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id if message.from_user else 0):
        await message.answer("❌ Lỗi: Bạn không có quyền thực hiện lệnh này!")
        return
    await state.set_state(AddGV.ins_id)
    await message.answer("Bắt đầu thêm GV mới. Bạn có thể gõ /cancel để hủy bất kỳ lúc nào.\n\n👉 1. Vui lòng nhập Mã Giáo Viên (VD: GV05):")

@dp.message(AddGV.ins_id)
async def add_gv_id(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("❌ Vui lòng nhập bằng văn bản/số!")
        return
    await state.update_data(ins_id=message.text.strip().upper())
    await state.set_state(AddGV.name)
    await message.answer("👉 2. Nhập Tên Giáo Viên (VD: Huyen):")

@dp.message(AddGV.name)
async def add_gv_name(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("❌ Vui lòng nhập bằng văn bản!")
        return
    await state.update_data(name=message.text.strip().upper())
    await state.set_state(AddGV.dept)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="YOGA", callback_data="dept_YOGA"), InlineKeyboardButton(text="GX", callback_data="dept_GX")]
    ])
    await message.answer("👉 3. Chọn Bộ Phận (Hoặc tự gõ chữ nếu là bộ phận khác):", reply_markup=kb)

@dp.message(AddGV.dept)
async def add_gv_dept(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("❌ Vui lòng nhập bằng văn bản!")
        return
    await state.update_data(dept=message.text.strip().upper())
    await state.set_state(AddGV.group_name)
    await message.answer("👉 4. Nhập Tên Nhóm/Phân loại (VD: FREELANCE, HẰNG TRẦN...):")

@dp.message(AddGV.group_name)
async def add_gv_group(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("❌ Vui lòng nhập bằng văn bản!")
        return
    await state.update_data(group_name=message.text.strip().upper())
    await state.set_state(AddGV.title)
    await message.answer("👉 5. Nhập Chức Danh (VD: MASTER, DANSPORT... Hoặc gõ - nếu không có):")

@dp.message(AddGV.title)
async def add_gv_title(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("❌ Vui lòng nhập bằng văn bản!")
        return
    title = message.text.strip().upper()
    if title == "-": title = ""
    await state.update_data(title=title)
    await state.set_state(AddGV.rate)
    await message.answer("👉 6. Nhập Giá 1 ca dạy (Chỉ nhập số, VD: 300000):")

@dp.message(AddGV.rate)
async def add_gv_rate(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("❌ Vui lòng nhập bằng văn bản/số!")
        return
    try:
        rate = int(message.text.strip())
        data = await state.get_data()
        await state.clear()
        
        ins_id = data['ins_id']
        ins_name = data['name']
        ins_dept = data['dept']
        ins_group = data['group_name']
        ins_title = data['title']
        ins_rate = rate
        
        new_ins = Instructor(id=ins_id, name=ins_name, department=ins_dept, group_name=ins_group, title=ins_title, base_rate=ins_rate)
        success = add_instructor(new_ins)
        if success:
            await message.answer(f"⏳ Đang đồng bộ giáo viên {ins_name} lên Google Sheets...")
            try:
                now = datetime.now()
                await asyncio.to_thread(add_instructor_to_sheets, now.month, now.year, ins_group, new_ins)
                await asyncio.to_thread(add_audit_log, message.from_user.id if message.from_user else 0, message.from_user.username if message.from_user else "", "ADD_GV", f"Thêm GV {ins_id} - {ins_name}")
                await message.answer(f"✅ Đã thêm giáo viên thành công:\n- Mã: {ins_id}\n- Tên: {ins_name}\n- Nhóm: {ins_group} ({ins_dept})\n- Giá: {ins_rate:,}đ")
            except Exception as e:
                await asyncio.to_thread(delete_instructor, ins_id)
                await message.answer(f"❌ Lỗi đồng bộ Google Sheets: {str(e)}\nĐã huỷ bỏ.")
        else:
            await message.answer("❌ Lỗi: Mã giáo viên này đã tồn tại trong hệ thống!")
    except ValueError:
        await message.answer("❌ Lỗi: Giá phải là số. Hãy nhập lại Giá (VD: 300000):")

# --- EDIT_GV FSM ---
@dp.message(Command("edit_gv"))
async def edit_gv_start(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id if message.from_user else 0):
        await message.answer("❌ Lỗi: Bạn không có quyền thực hiện lệnh này!")
        return
    await state.set_state(EditGV.ins_id)
    await message.answer("Bắt đầu sửa thông tin GV. Gõ /cancel để hủy.\n\n👉 Nhập Mã Giáo Viên cần sửa (VD: GV05):")

@dp.message(EditGV.ins_id)
async def edit_gv_id(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("❌ Vui lòng nhập bằng văn bản!")
        return
    ins_id = message.text.strip().upper()
    old_ins = get_instructor_by_id(ins_id)
    if not old_ins:
        await message.answer("❌ Không tìm thấy giáo viên với mã này. Hãy thử nhập lại hoặc gõ /cancel.")
        return
    await state.update_data(ins_id=ins_id, old_ins=old_ins)
    await state.set_state(EditGV.name)
    await message.answer(f"Đang sửa GV: {old_ins['name']}\n👉 Nhập Tên MỚI (Gửi dấu `-` để giữ nguyên tên cũ `{old_ins['name']}`):")

@dp.message(EditGV.name)
async def edit_gv_name(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("❌ Vui lòng nhập bằng văn bản!")
        return
    text = message.text.strip().upper()
    data = await state.get_data()
    if text != "-":
        await state.update_data(name=text)
    else:
        await state.update_data(name=data['old_ins']['name'])
    await state.set_state(EditGV.dept)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="YOGA", callback_data="dept_YOGA"), InlineKeyboardButton(text="GX", callback_data="dept_GX")]
    ])
    await message.answer(f"👉 Chọn Bộ Phận MỚI (Hoặc tự gõ. Gửi `-` để giữ nguyên `{data['old_ins']['department']}`):", reply_markup=kb)
    
@dp.message(EditGV.dept)
async def edit_gv_dept(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("❌ Vui lòng nhập bằng văn bản!")
        return
    text = message.text.strip().upper()
    data = await state.get_data()
    if text != "-":
        await state.update_data(dept=text)
    else:
        await state.update_data(dept=data['old_ins']['department'])
    await state.set_state(EditGV.group_name)
    await message.answer(f"👉 Nhập Nhóm MỚI (Gửi `-` để giữ nguyên `{data['old_ins']['group_name']}`):")

@dp.message(EditGV.group_name)
async def edit_gv_group(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("❌ Vui lòng nhập bằng văn bản!")
        return
    text = message.text.strip().upper()
    data = await state.get_data()
    if text != "-":
        await state.update_data(group_name=text)
    else:
        await state.update_data(group_name=data['old_ins']['group_name'])
    await state.set_state(EditGV.title)
    await message.answer(f"👉 Nhập Chức Danh MỚI (Gửi `-` để giữ nguyên `{data['old_ins']['title']}`):")

@dp.message(EditGV.title)
async def edit_gv_title(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("❌ Vui lòng nhập bằng văn bản!")
        return
    text = message.text.strip().upper()
    data = await state.get_data()
    if text != "-":
        if text == "NONE" or text == "KHÔNG": text = ""
        await state.update_data(title=text)
    else:
        await state.update_data(title=data['old_ins']['title'])
    await state.set_state(EditGV.rate)
    await message.answer(f"👉 Nhập Giá MỚI (Gửi `-` để giữ nguyên `{data['old_ins']['base_rate']}`):")

@dp.message(EditGV.rate)
async def edit_gv_rate(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("❌ Vui lòng nhập bằng văn bản/số!")
        return
    text = message.text.strip()
    data = await state.get_data()
    old_ins = data['old_ins']
    try:
        rate = int(text) if text != "-" else old_ins['base_rate']
        await state.clear()
        
        ins_id = data['ins_id']
        ins_name = data['name']
        ins_dept = data['dept']
        ins_group = data['group_name']
        ins_title = data['title']
        ins_rate = rate
        
        success = update_instructor_details(ins_id, ins_name, ins_dept, ins_group, ins_title, ins_rate)
        if success:
            await message.answer(f"⏳ Đang đồng bộ thay đổi lên Google Sheets...")
            try:
                now = datetime.now()
                new_ins = Instructor(id=ins_id, name=ins_name, department=ins_dept, group_name=ins_group, title=ins_title, base_rate=ins_rate)
                await asyncio.to_thread(update_instructor_on_sheets, now.month, now.year, old_ins["name"], old_ins["group_name"], new_ins)
                await asyncio.to_thread(add_audit_log, message.from_user.id if message.from_user else 0, message.from_user.username if message.from_user else "", "EDIT_GV", f"Sửa GV {ins_id}")
                await message.answer(f"✅ Đã cập nhật giáo viên thành công!")
            except Exception as e:
                update_instructor_details(ins_id, old_ins["name"], old_ins["department"], old_ins["group_name"], old_ins["title"], old_ins["base_rate"])
                await message.answer(f"❌ Lỗi đồng bộ Google Sheets: {str(e)}\nĐã huỷ bỏ cập nhật.")
        else:
            await message.answer("❌ Lỗi cập nhật cơ sở dữ liệu!")
    except ValueError:
        await message.answer("❌ Lỗi: Giá phải là số. Nhập lại hoặc gõ `-`:")

# --- DEL_GV FSM ---
@dp.message(Command("del_gv"))
async def del_gv_start(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id if message.from_user else 0):
        await message.answer("❌ Lỗi: Bạn không có quyền thực hiện lệnh này!")
        return
    await state.set_state(DelGV.ins_id)
    await message.answer("👉 Nhập Mã Giáo Viên cần xóa (VD: GV05):")

@dp.message(DelGV.ins_id)
async def del_gv_id(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("❌ Vui lòng nhập bằng văn bản!")
        return
    ins_id = message.text.strip().upper()
    old_ins = get_instructor_by_id(ins_id)
    if not old_ins:
        await message.answer("❌ Không tìm thấy giáo viên với mã này. Thử lại hoặc /cancel.")
        return
    await state.update_data(ins_id=ins_id, old_ins=old_ins)
    await state.set_state(DelGV.confirm)
    await message.answer(f"⚠️ CẢNH BÁO: Bạn có chắc chắn muốn xóa giáo viên **{old_ins['name']}** ({ins_id}) khỏi hệ thống?\n👉 Gõ `YES` để xác nhận, hoặc gõ bất kỳ chữ gì để hủy.")

@dp.message(DelGV.confirm)
async def del_gv_confirm(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("❌ Vui lòng nhập bằng văn bản!")
        return
    text = message.text.strip().upper()
    data = await state.get_data()
    await state.clear()
    
    if text != "YES":
        await message.answer("✅ Đã hủy lệnh xóa giáo viên.")
        return
        
    ins_id = data['ins_id']
    old_ins = data['old_ins']
    ins_name = old_ins["name"]
    
    success = delete_instructor(ins_id)
    if success:
        await message.answer(f"⏳ Đang xóa {ins_name} khỏi Google Sheets...")
        try:
            now = datetime.now()
            await asyncio.to_thread(delete_instructor_from_sheets, now.month, now.year, ins_name)
            await asyncio.to_thread(add_audit_log, message.from_user.id if message.from_user else 0, message.from_user.username if message.from_user else "", "DEL_GV", f"Xóa GV {ins_id}")
            await message.answer(f"✅ Đã xóa giáo viên {ins_name} thành công!")
        except Exception as e:
            add_instructor(Instructor(id=ins_id, name=ins_name, department=old_ins["department"], group_name=old_ins["group_name"], title=old_ins["title"], base_rate=old_ins["base_rate"]))
            await message.answer(f"❌ Lỗi xoá trên Google Sheets: {str(e)}\nĐã Rollback DB.")
    else:
        await message.answer("❌ Lỗi xóa khỏi cơ sở dữ liệu!")

# --- EXISTING HANDLERS ---
@dp.message(Command("list_gv"))
async def list_instructor_handler(message: Message) -> None:
    instructors = get_all_instructors()
    if not instructors:
        await message.answer("Danh sách giáo viên hiện đang trống.")
        return
        
    response = "📋 **DANH SÁCH GIÁO VIÊN**\n\n"
    for ins in instructors:
        line = f"- `{ins['id']}` | {ins['name']} | Bộ môn: {ins['department']} | Nhóm: {ins['group_name']} | Giá: {ins['base_rate']:,}đ\n"
        if len(response) + len(line) > 4000:
            await message.answer(response, parse_mode="Markdown")
            response = ""
        response += line
        
    if response:
        await message.answer(response, parse_mode="Markdown")


@dp.message(Command("fix_bonus"))
async def fix_bonus_handler(message: Message) -> None:
    if not is_admin(message.from_user.id if message.from_user else 0):
        await message.answer("❌ Lỗi: Bạn không có quyền thực hiện lệnh này!")
        return

    now = datetime.now()
    status_msg = await message.answer(f"⏳ Đang đồng bộ lại thưởng/phạt Tháng {now.month}/{now.year}...")
    try:
        from export_service.excel_writer import sync_bonus_adjustments_from_db
        updated_rows, errors = await asyncio.to_thread(sync_bonus_adjustments_from_db, now.month, now.year)
        report = f"✅ Đã đồng bộ thưởng/phạt.\n- Tháng: {now.month}/{now.year}\n- Số dòng cập nhật: {updated_rows}"
        if errors:
            report += f"\n- Lỗi: {len(errors)}"
        await bot.edit_message_text(report, chat_id=message.chat.id, message_id=status_msg.message_id)
    except Exception as e:
        await bot.edit_message_text(f"❌ Lỗi đồng bộ thưởng/phạt: {e}", chat_id=message.chat.id, message_id=status_msg.message_id)

# --- UNDO FSM ---
@dp.message(Command("undo"))
async def undo_start(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id if message.from_user else 0):
        await message.answer("❌ Lỗi: Bạn không có quyền thực hiện lệnh này!")
        return
    await state.set_state(UndoFSM.file_hash)
    await message.answer("👉 Nhập Mã File (8 ký tự) bạn muốn thu hồi dữ liệu (hoặc gõ /cancel để hủy):")

@dp.message(UndoFSM.file_hash)
async def undo_process(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("❌ Vui lòng nhập mã file bằng văn bản!")
        return
    file_hash = message.text.strip()
    await state.clear()
    
    status_msg = await message.answer(f"⏳ Đang thu hồi dữ liệu của file `{file_hash[:8]}`...")
    
    try:
        from instructor_service.database import get_full_hash, is_file_processed, get_logs_by_file_hash, delete_logs_by_file_hash, remove_processed_file
        from export_service.excel_writer import rollback_instructor_works_batch
        
        full_hash = get_full_hash(file_hash)
        
        if not full_hash:
            await bot.edit_message_text(f"❌ Lỗi: Không tìm thấy mã file `{file_hash}` trong hệ thống hoặc đã bị thu hồi.", 
                                       chat_id=message.chat.id, 
                                       message_id=status_msg.message_id)
            return
            
        file_hash = full_hash
        logs = get_logs_by_file_hash(file_hash)
        if not logs:
            remove_processed_file(file_hash)
            await bot.edit_message_text(f"✅ Đã thu hồi file `{file_hash[:8]}`.", chat_id=message.chat.id, message_id=status_msg.message_id)
            return
            
        from collections import defaultdict
        from datetime import date
        logs_by_month = defaultdict(list)
        for log in logs:
            if isinstance(log["date"], date):
                m = log["date"].month
                y = log["date"].year
            else:
                y, m, d = map(int, str(log["date"]).split("-"))
            logs_by_month[(m, y)].append(log)
            
        total_rolled_back = 0
        errors = []
        for (m, y), month_logs in logs_by_month.items():
            success_count, errs = await asyncio.to_thread(rollback_instructor_works_batch, m, y, month_logs)
            total_rolled_back += success_count
            errors.extend(errs)
            
        delete_logs_by_file_hash(file_hash)
        remove_processed_file(file_hash)
        add_audit_log((message.from_user.id if message.from_user else 0), (message.from_user.username if message.from_user else ""), "UNDO", f"Thu hồi file {file_hash[:8]}")
        
        report = f"✅ Đã thu hồi thành công!\n- Mã File: `{file_hash[:8]}`\n- Số ca dạy được rút lại: {len(logs)} ca.\n"
        if errors:
            report += f"\n⚠️ Lưu ý có {len(errors)} lỗi khi trừ trên Sheets:\n"
            for err in errors[:5]:
                report += f"- {err}\n"
                
        await bot.edit_message_text(report, chat_id=message.chat.id, message_id=status_msg.message_id)
        
    except Exception as e:
        print(f"Lỗi undo: {e}")
        await bot.edit_message_text(f"❌ Có lỗi hệ thống khi thu hồi dữ liệu. Vui lòng thử lại sau.", chat_id=message.chat.id, message_id=status_msg.message_id)


# Tách logic xử lý file Excel ra background task để chống Timeout Webhook
async def background_process_excel(message: Message, status_msg: Message, document: Document, file_info):
    tmp_path = ""
    try:
        import hashlib
        from instructor_service.database import is_file_processed, record_processed_file
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_file:
            tmp_path = tmp_file.name
            
        if file_info.file_path:
            await bot.download_file(file_info.file_path, destination=tmp_path)
            
        file_hash = ""
        with open(tmp_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
            
        if is_file_processed(file_hash):
            os.remove(tmp_path)
            tmp_path = ""
            await bot.edit_message_text("❌ Lỗi: File này đã được gửi và tính công trước đó rồi.\nHệ thống từ chối xử lý để chống nhân đôi lương!", 
                                       chat_id=message.chat.id, message_id=status_msg.message_id)
            return
        
        await bot.edit_message_text("⚙️ Đang phân tích và cập nhật vào Bảng Master...", chat_id=message.chat.id, message_id=status_msg.message_id)
                                   
        result = await asyncio.to_thread(process_timesheet, tmp_path, file_hash)
        os.remove(tmp_path)
        tmp_path = ""
        
        success_count = result.get("success", 0)
        errors = result.get("errors", [])
        sheet_failed = bool(result.get("sheet_failed", False))
        if success_count > 0 and not sheet_failed:
            record_processed_file(file_hash, document.file_name)
            add_audit_log((message.from_user.id if message.from_user else 0), (message.from_user.username if message.from_user else ""), "UPLOAD", f"Tải lên file {document.file_name} ({success_count} ca)")
            from export_service.excel_writer import sync_bonus_adjustments_from_db
            processed_months = result.get("processed_months") or []
            if not processed_months:
                now = datetime.now()
                processed_months = [{"month": now.month, "year": now.year}]
            for item in processed_months:
                await asyncio.to_thread(sync_bonus_adjustments_from_db, int(item["month"]), int(item["year"]))
            
        errors = result.get("errors", [])
        report = f"✅ Xử lý hoàn tất!\n- Mã File: `{file_hash[:8]}`\n- Số ca thành công: {success_count}\n"
        if sheet_failed:
            report += "- File chua duoc danh dau da xu ly do co loi ghi Google Sheets.\n"
        if errors:
            report += f"- Số ca bị lỗi/không tính công: {len(errors)}\n\nChi tiết lỗi:\n"
            for err in errors[:10]:
                report += f"⚠️ {err}\n"
            if len(errors) > 10:
                report += f"... và {len(errors) - 10} lỗi khác."
                
        await bot.edit_message_text(report, chat_id=message.chat.id, message_id=status_msg.message_id)
        
    except Exception as e:
        print(f"Lỗi process excel: {e}")
        await bot.edit_message_text("❌ Có lỗi hệ thống nghiêm trọng khi xử lý file. Vui lòng liên hệ Admin!", chat_id=message.chat.id, message_id=status_msg.message_id)

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

@dp.message(F.document)
async def handle_excel_document(message: Message):
    if not is_admin(message.from_user.id if message.from_user else 0):
        await message.answer("❌ Lỗi: Bạn không có quyền upload file chấm công!")
        return
        
    document = message.document
    if not document:
        return
        
    if not document.file_name or not document.file_name.endswith(('.xlsx', '.xls')):
        await message.answer("❌ Vui lòng gửi file Excel (.xlsx hoặc .xls)")
        return
        
    status_msg = await message.answer("⏳ Đang tiếp nhận file và đưa vào hàng chờ xử lý...")
    
    try:
        # Lấy file_info ngay lập tức để tránh lỗi URL hết hạn
        file_info = await bot.get_file(document.file_id)
        # Bắn task chạy ngầm, trả luồng chính về cho Webhook ngay lập tức
        asyncio.create_task(background_process_excel(message, status_msg, document, file_info))
    except Exception as e:
        print(f"Lỗi khởi tạo tải file: {e}")
        await bot.edit_message_text("❌ Có lỗi khi tải file từ Telegram. Vui lòng thử lại.", chat_id=message.chat.id, message_id=status_msg.message_id)

# --- CLOSE FSM ---
@dp.message(Command("close"))
async def close_start(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id if message.from_user else 0):
        await message.answer("❌ Lỗi: Bạn không có quyền thực hiện lệnh này!")
        return
    await state.set_state(CloseFSM.month_year)
    now = datetime.now()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Tháng Hiện Tại ({now.month}/{now.year})", callback_data=f"close_month_{now.month}_{now.year}")],
        [InlineKeyboardButton(text="Tháng Trước", callback_data=f"close_month_{now.month-1 if now.month>1 else 12}_{now.year if now.month>1 else now.year-1}")]
    ])
    await message.answer("👉 Chọn hoặc Nhập Tháng và Năm cần CHỐT LƯƠNG (VD: `06/2026`):", reply_markup=kb)

@dp.message(CloseFSM.month_year)
async def close_process(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("❌ Vui lòng nhập bằng văn bản!")
        return
    
    text = message.text.strip().replace("/", " ")
    parts = text.split()
    if len(parts) != 2:
        await message.answer("❌ Sai định dạng! Vui lòng nhập lại (VD: `06/2026` hoặc `6 2026`):")
        return
        
    try:
        month, year = int(parts[0]), int(parts[1])
        await state.clear()
        status_msg = await message.answer(f"⏳ Đang khóa bảng công Tháng {month}/{year} trên Google Sheets...")
        
        from export_service.excel_writer import sync_bonus_adjustments_from_db
        await asyncio.to_thread(sync_bonus_adjustments_from_db, month, year)
        from export_service.sheet_manager import lock_worksheet
        success = await asyncio.to_thread(lock_worksheet, month, year)
        
        if success:
            add_audit_log((message.from_user.id if message.from_user else 0), (message.from_user.username if message.from_user else ""), "CLOSE_SHEET", f"Khóa lương tháng {month}/{year}")
            await bot.edit_message_text(f"🔒 Đã khóa thành công bảng lương Tháng {month}/{year}! Mọi nhân sự sẽ không thể chỉnh sửa trang tính này nữa.", chat_id=message.chat.id, message_id=status_msg.message_id)
        else:
            await bot.edit_message_text("❌ Có lỗi xảy ra khi gọi Google Sheets API để khóa.", chat_id=message.chat.id, message_id=status_msg.message_id)
            
    except ValueError:
        await message.answer("❌ Lỗi: Tháng và Năm phải là số! Vui lòng nhập lại (VD: `06/2026`):")
    except Exception as e:
        print(f"Lỗi close handler: {e}")
        await state.clear()
        await message.answer("❌ Có lỗi hệ thống. Vui lòng thử lại sau.")

# --- REPORT FSM ---
@dp.message(Command("report"))
async def report_start(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id if message.from_user else 0):
        await message.answer("❌ Lỗi: Bạn không có quyền thực hiện lệnh này!")
        return
    await state.set_state(ReportFSM.month_year)
    now = datetime.now()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Tháng Hiện Tại ({now.month}/{now.year})", callback_data=f"report_month_{now.month}_{now.year}")],
        [InlineKeyboardButton(text="Tháng Trước", callback_data=f"report_month_{now.month-1 if now.month>1 else 12}_{now.year if now.month>1 else now.year-1}")]
    ])
    await message.answer("👉 Chọn hoặc Nhập Tháng và Năm cần xuất Báo cáo (VD: `06/2026`):", reply_markup=kb)

@dp.message(ReportFSM.month_year)
async def report_process(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("❌ Vui lòng nhập bằng văn bản!")
        return
    
    text = message.text.strip().replace("/", " ")
    parts = text.split()
    if len(parts) != 2:
        await message.answer("❌ Sai định dạng! Vui lòng nhập lại (VD: `06/2026` hoặc `6 2026`):")
        return
        
    try:
        month, year = int(parts[0]), int(parts[1])
        await state.clear()
        await message.answer(f"⏳ Đang tổng hợp báo cáo quỹ lương Tháng {month}/{year}...")
        
        from payroll_engine.report import generate_monthly_report
        report_text = await asyncio.to_thread(generate_monthly_report, month, year)
        
        add_audit_log((message.from_user.id if message.from_user else 0), (message.from_user.username if message.from_user else ""), "REPORT", f"Xem báo cáo tháng {month}/{year}")
        await message.answer(report_text, parse_mode="Markdown")
        
    except ValueError:
        await message.answer("❌ Lỗi: Tháng và Năm phải là số! Vui lòng nhập lại (VD: `06/2026`):")
    except Exception as e:
        print(f"Lỗi report handler: {e}")
        await state.clear()
        await message.answer("❌ Có lỗi hệ thống khi sinh báo cáo. Vui lòng thử lại sau.")

# --- CHECK FSM ---
@dp.message(Command("check"))
async def check_start(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id if message.from_user else 0):
        await message.answer("❌ Lỗi: Bạn không có quyền thực hiện lệnh này!")
        return
    await state.set_state(CheckFSM.month_year)
    now = datetime.now()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Tháng Hiện Tại ({now.month}/{now.year})", callback_data=f"check_month_{now.month}_{now.year}")],
        [InlineKeyboardButton(text="Tháng Trước", callback_data=f"check_month_{now.month-1 if now.month>1 else 12}_{now.year if now.month>1 else now.year-1}")]
    ])
    await message.answer("👉 Chọn hoặc Nhập Tháng và Năm cần tra cứu (VD: `06/2026`):\n💡 Hoặc chỉ cần gõ `nay` để tra cứu tháng hiện tại:", reply_markup=kb)

@dp.message(CheckFSM.month_year)
async def check_month(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("❌ Vui lòng nhập bằng văn bản!")
        return
        
    text = message.text.strip().lower()
    
    if text == "nay":
        from datetime import datetime
        now = datetime.now()
        month, year = now.month, now.year
    else:
        text = text.replace("/", " ")
        parts = text.split()
        if len(parts) != 2:
            await message.answer("❌ Sai định dạng! Vui lòng nhập lại (VD: `06/2026` hoặc gõ `nay`):")
            return
        try:
            month, year = int(parts[0]), int(parts[1])
        except ValueError:
            await message.answer("❌ Lỗi: Tháng và Năm phải là số! Vui lòng nhập lại:")
            return
            
    await state.update_data(month=month, year=year)
    await state.set_state(CheckFSM.query)
    await message.answer(f"Đã chọn Tháng {month}/{year}.\n👉 Bây giờ hãy nhập Từ khóa (Mã GV, Tên GV, hoặc Tên Nhóm. VD: `GV01` hoặc `YOGA`):")

@dp.message(CheckFSM.query)
async def check_process(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("❌ Vui lòng nhập bằng văn bản!")
        return
        
    query = message.text.strip()
    data = await state.get_data()
    month, year = data['month'], data['year']
    await state.clear()
    
    try:
        from payroll_engine.report import generate_check_report
        await message.answer(f"⏳ Đang tra cứu `{query}` trong Tháng {month}/{year}...")
        report_text = await asyncio.to_thread(generate_check_report, month, year, query)
        
        await asyncio.to_thread(add_audit_log, (message.from_user.id if message.from_user else 0), (message.from_user.username if message.from_user else ""), "CHECK", f"Tra cứu {query} tháng {month}/{year}")
        await message.answer(report_text, parse_mode="Markdown")
    except Exception as e:
        print(f"Lỗi check handler: {e}")
        await message.answer("❌ Có lỗi hệ thống khi tra cứu. Vui lòng thử lại sau.")


async def on_startup(bot: Bot):
    if WEBHOOK_URL:
        await bot.set_webhook(WEBHOOK_URL, allowed_updates=dp.resolve_used_update_types())

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()

async def main():
    if not TOKEN or TOKEN == "nhap_token_cua_ban_vao_day":
        print("LỖI: Chưa có TELEGRAM_BOT_TOKEN trong file .env!")
        return

    global bot
    if bot is None:
        bot = Bot(token=TOKEN)

    if WEBHOOK_URL:
        print(f"Khởi động Bot chế độ Webhook... URL: {WEBHOOK_URL}")
        # Webhook setup
        dp.startup.register(on_startup)
        dp.shutdown.register(on_shutdown)
        
        app = web.Application()
        webhook_requests_handler = SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
        )
        webhook_requests_handler.register(app, path="/webhook")
        setup_application(app, dp, bot=bot)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, WEBAPP_HOST, WEBAPP_PORT)
        await site.start()
        print(f"Đang lắng nghe tại http://{WEBAPP_HOST}:{WEBAPP_PORT}/webhook")
        
        # Chạy vĩnh viễn
        await asyncio.Event().wait()
    else:
        print("Khởi động Bot chế độ Long-Polling...")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot đã dừng.")

