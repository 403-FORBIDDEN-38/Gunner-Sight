@echo off
REM GunnerSight build script (Nuitka onedir, plain-text config)
REM Usage: double-click, or run tools\build.bat from any directory
REM        (the script cd's to the repo root itself).
REM Output: dist\main.dist\GUNNER SIGHT.exe
REM
REM IMPORTANT: keep this file PURE ASCII and CRLF.
REM   - cmd.exe splits lines on CR, so LF-only breaks Chinese/echo lines.
REM   - the batch parser under cp65001 drops bytes of multi-byte chars
REM     (real incident: 'echo <CJK> path' was split into 'echo <char>' +
REM     an unknown command). ASCII text is the only deterministic fix.
REM
REM Keep Nuitka's C cache (main.build); deleting it forces full rebuilds.

setlocal
cd /d "%~dp0.."

REM ---- interpreter selection (P2): prefer uv run, fallback to py launcher ----
set PY_RUN=py
where uv >nul 2>nul
if %errorlevel%==0 set PY_RUN=uv run --with nuitka --with zstandard python

REM ---- auto backup before build: refresh backups\auto_before_build (no accumulation) ----
robocopy . backups\auto_before_build /MIR /XD .git .venv dist backups .workbuddy __pycache__ .pytest_cache .ruff_cache /XF *.pyc *.pyo /NFL /NDL /NJH /NJS /R:1 /W:1 >nul
if %errorlevel% geq 8 echo [WARN] auto backup failed, continuing anyway

echo [1/2] Cleaning old output (keeping build cache)...
if exist "dist\main.dist" rmdir /s /q "dist\main.dist"

echo [2/2] Nuitka compiling (cache reused)...
%PY_RUN% -m nuitka --version >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] nuitka not found. Install build deps first:
    echo   - uv users:  uv sync --extra build
    echo   - pip users: py -m pip install nuitka zstandard
    echo   First build also downloads the MinGW C compiler, about 100MB.
    exit /b 1
)
for /f "delims=" %%v in ('%PY_RUN% -c "from gui.tabs.info_tab import APP_VERSION; v=APP_VERSION.lstrip('V'); p=v.split('.'); print(f'{p[0]}.{p[1][0:2]}.{p[1][2:5]}.{int(p[1][5:])}')"') do set APP_VER=%%v
if not defined APP_VER set APP_VER=0.0.0.0
%PY_RUN% -m nuitka main.py ^
    --standalone ^
    --enable-plugin=pyqt5 ^
    --windows-icon-from-ico=resources/app_icon.ico ^
    --copyright="Copyright (C) 2026 [403 FORBIDDEN]. Dedicated to Xiaocheng." ^
    --product-version=%APP_VER% ^
    --include-data-files=docs/CREDITS.md=CREDITS.md ^
    --include-data-files=README.md=README.md ^
    --include-data-files=USER_GUIDE.md=USER_GUIDE.md ^
    --include-data-files=LICENSE=LICENSE ^
    --include-data-files=docs/THIRD_PARTY_NOTICES.md=THIRD_PARTY_NOTICES.md ^
    --output-filename="GUNNER SIGHT.exe" ^
    --python-flag=no_docstrings ^
    --python-flag=no_asserts ^
    --python-flag=isolated ^
    --python-flag=safe_path ^
    --include-data-dir=resources=resources ^
    --include-data-dir=config=config ^
    --jobs=%NUMBER_OF_PROCESSORS% ^
    --output-dir=dist ^
    --assume-yes-for-downloads ^
    --windows-console-mode=disable

if %errorlevel% neq 0 (
    echo [ERROR] build failed with code %errorlevel%
    exit /b %errorlevel%
)

echo.
echo Build complete.
echo Output: "%cd%\dist\main.dist\GUNNER SIGHT.exe"
echo Next: copy the whole dist\main.dist over the portable install folder.
echo.
pause
