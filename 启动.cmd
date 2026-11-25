@echo off
setlocal
pushd "%~dp0" || goto failed
if not exist ".venv\Scripts\python.exe" (
    echo Project Python was not found at .venv\Scripts\python.exe.
    popd
    goto failed
)
set "PYTHONPATH=%CD%\src"
".venv\Scripts\python.exe" -m flashunstander
if errorlevel 1 (
    popd
    goto failed
)
popd
exit /b 0

:failed
echo flashUnstander did not start successfully. See the message above.
pause
exit /b 1
