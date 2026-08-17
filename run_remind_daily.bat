@echo off
rem OfferLoop 每日主动提醒 —— 由 Windows 任务计划程序每天 22:00 调用
rem 切到项目目录（保证 from src.memory import ... 能解析），再静默检查遗忘状态
cd /d D:\AIWorkspace\OfferLoop\offerloop
D:\ProgramData\anaconda3\python.exe run_remind.py --notify >> D:\AIWorkspace\OfferLoop\offerloop\remind_daily.log 2>&1
