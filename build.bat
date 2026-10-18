@echo off
REM GunnerSight 打包脚本（Nuitka onedir，配置明文）
REM 用法：双击 build.bat，或命令行执行 build.bat
REM 产物：dist\main.dist\GUNNER SIGHT.exe
REM 说明：开发版与发布版已无区别（config 明文，加密已取消），本脚本即发布脚本。
REM
REM 注意：本文件必须保持 CRLF 换行！cmd.exe 按 CR 分行，LF-only 会让含中文的
REM       echo 行被拆成命令执行（build_err.txt 的乱码根源，chcp 解决不了）。
REM
REM 复用编译缓存：只清产物 main.dist，保留 main.build（Nuitka 的 C 编译缓存）。
REM 删掉 main.build 会退化成每次全量重编，慢很多。

setlocal
cd /d "%~dp0"

echo [1/2] 清理旧产物（保留编译缓存 main.build）...
if exist "dist\main.dist" rmdir /s /q "dist\main.dist"

echo [2/2] Nuitka 编译中（复用缓存，用时取决于改动范围）...
for /f "delims=" %%v in ('py -c "from gui.tabs.info_tab import APP_VERSION; v=APP_VERSION.lstrip('V'); p=v.split('.'); print(f'{p[0]}.{p[1][0:2]}.{p[1][2:5]}.{int(p[1][5:])}')"') do set APP_VER=%%v
py -m nuitka main.py ^
    --standalone ^
    --enable-plugin=pyqt5 ^
    --windows-icon-from-ico=app_icon.ico ^
    --copyright="Copyright © 2026 [403 FORBIDDEN]. Dedicated to Xiaocheng." ^
    --product-version=%APP_VER% ^
    --include-data-files=CREDITS.md=CREDITS.md ^
    --include-data-files=README.md=README.md ^
    --include-data-files=USER_GUIDE.md=USER_GUIDE.md ^
    --include-data-files=LICENSE=LICENSE ^
    --output-filename="GUNNER SIGHT.exe" ^
    --python-flag=no_docstrings ^
    --python-flag=no_asserts ^
    --python-flag=isolated ^
    --python-flag=safe_path ^
    --include-data-dir=resources=resources ^
    --include-data-dir=config=config ^
    --jobs=8 ^
    --output-dir=dist ^
    --assume-yes-for-downloads ^
    --windows-console-mode=disable

if %errorlevel% neq 0 (
    echo [ERROR] 编译失败，错误码 %errorlevel%
    exit /b %errorlevel%
)

echo.
echo 编译完成！
echo 产物路径: %cd%\dist\main.dist\GUNNER SIGHT.exe
echo 下一步: 把 dist\main.dist 整个目录复制覆盖到桌面版目录
echo.
pause
