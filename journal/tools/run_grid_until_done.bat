@echo off
cd /d "%~dp0"
set PYTHONUNBUFFERED=1
echo fresh start
python -u grid_tv_custom_balance.py
:loop
if %ERRORLEVEL%==0 goto done
if %ERRORLEVEL%==1 goto fail
echo resume after exit %ERRORLEVEL%
python -u grid_tv_custom_balance.py --resume
goto loop
:done
echo DONE
exit /b 0
:fail
echo FAILED
exit /b 1
