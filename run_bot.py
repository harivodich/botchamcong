import asyncio
from api_gateway.bot import main
from instructor_service.backup_service import run_backup
from datetime import datetime, timedelta

async def backup_scheduler():
    while True:
        now = datetime.now()
        # Tính toán thời gian ngủ cho đến 00:00 ngày mai
        next_run = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        sleep_seconds = (next_run - now).total_seconds()
        
        print(f"⏳ Hẹn giờ Backup tự động vào lúc: {next_run.strftime('%Y-%m-%d %H:%M:%S')} (ngủ {sleep_seconds:.0f} giây)")
        await asyncio.sleep(sleep_seconds)
        
        # Chạy backup khi thức dậy
        run_backup()

async def run_all():
    # Chạy đồng thời bot và scheduler
    task1 = asyncio.create_task(main())
    task2 = asyncio.create_task(backup_scheduler())
    await asyncio.gather(task1, task2)

if __name__ == "__main__":
    try:
        asyncio.run(run_all())
    except KeyboardInterrupt:
        print("Bot đã được tắt an toàn.")
