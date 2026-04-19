@echo off
REM AI手札 — Windows 定时任务安装脚本
REM 每天 08:00 自动运行编排器

echo ====================================
echo  AI手札 - 安装每日定时任务
echo ====================================

set PROJECT_DIR=%~dp0..
set PYTHON=python
set SCRIPT=%PROJECT_DIR%\scripts\orchestrator.py

echo 项目目录: %PROJECT_DIR%
echo 脚本路径: %SCRIPT%

schtasks /create ^
    /tn "AI手札-每日更新" ^
    /tr "%PYTHON% %SCRIPT%" ^
    /sc daily ^
    /st 08:00 ^
    /f

if %errorlevel% == 0 (
    echo.
    echo 定时任务创建成功!
    echo    任务名: AI手札-每日更新
    echo    执行时间: 每天 08:00
    echo.
    echo 管理命令:
    echo    查看: schtasks /query /tn "AI手札-每日更新"
    echo    删除: schtasks /delete /tn "AI手札-每日更新" /f
    echo    手动运行: schtasks /run /tn "AI手札-每日更新"
) else (
    echo 创建失败! 请以管理员权限运行此脚本
)
pause
