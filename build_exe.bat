@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Majestic Text Helper - сборка EXE
set "PYTHONUTF8=1"
echo === Majestic Text Helper: сборка EXE (v3.6.0) ===
echo.
cd /d "%~dp0"

REM --- v3.6.0: bat переписан. Исправлено: ---
REM  * если "python" не найден или открывает Microsoft Store — пробуем "py -3";
REM  * проверяем, что PyInstaller реально установлен, и ставим при отсутствии;
REM  * PYTHONUTF8=1 — не зависит от кодовой страницы консоли;
REM  * каждая ошибка объясняется и ставит сборку на паузу (окно не закроется).

set "PY="
python --version >nul 2>&1
if not errorlevel 1 set "PY=python"
if "%PY%"=="" (
  py -3 --version >nul 2>&1
  if not errorlevel 1 set "PY=py -3"
)
if "%PY%"=="" (
  echo [ОШИБКА] Python не найден. Установите Python 3.10+ с python.org
  echo и при установке отметьте галочку "Add Python to PATH".
  echo Если установили — перезапустите этот файл.
  pause
  exit /b 1
)
echo Найден Python:  %PY%
%PY% --version

echo.
echo [1/4] Установка зависимостей (PySide6, keyboard, PyInstaller)...
%PY% -m pip install --upgrade pip >nul 2>&1
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ОШИБКА] Не удалось установить зависимости. Проверьте интернет
  echo или отключите антивирус на время сборки.
  pause
  exit /b 1
)

%PY% -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
  echo [!] PyInstaller не установился - ставлю отдельно...
  %PY% -m pip install "pyinstaller>=6.0"
  if errorlevel 1 (
    echo [ОШИБКА] PyInstaller не установился. Пришлите текст ошибки разработчику.
    pause
    exit /b 1
  )
)

echo.
echo [2/4] Сборка основной версии (PyInstaller, 1-3 минуты)...
%PY% -m PyInstaller --clean -y majestic_helper.spec
if errorlevel 1 (
  echo [ОШИБКА] Сборка не удалась. Частые причины:
  echo   * антивирус заблокировал сборку - добавьте папку в исключения;
  echo   * путь к папке содержит кириллицу - перенесите в C:\MTH\;
  echo   * не хватает места на диске.
  echo Пришлите разработчику текст ошибки сверху.
  pause
  exit /b 1
)

echo.
echo [3/4] Сборка диагностической версии (с окном консоли)...
%PY% -m PyInstaller -y majestic_helper_debug.spec
if errorlevel 1 (
  echo [ВНИМАНИЕ] Диагностическая версия не собралась - основная всё равно готова.
)

echo.
echo [4/4] Готово!
if exist dist\MajesticTextHelper\MajesticTextHelper.exe (
  echo ============================================================
  echo  УСПЕХ!
  echo.
  echo  Программа:      dist\MajesticTextHelper\MajesticTextHelper.exe
  echo  Запускайте ИМЕННО его - из папки MajesticTextHelper.
  echo  Папку можно перенести куда угодно ЦЕЛИКОМ (вместе с _internal).
  echo.
  echo  Диагностика:    dist\MajesticTextHelper_debug\MajesticTextHelper_debug.exe
  echo  У неё видно чёрное окно консоли с ошибками - если основная
  echo  версия не открывается, запустите её и сфотографируйте текст.
  echo.
  echo  Данные хранятся рядом: data\data.json
  echo  При запуске Windows спросит права администратора - жмите "Да".
  echo ============================================================
) else (
  echo [ОШИБКА] dist\MajesticTextHelper\MajesticTextHelper.exe не найден.
  echo Скорее всего антивирус удалил exe сразу после сборки.
  echo Добавьте папку проекта в исключения антивируса и соберите заново.
)
pause
endlocal
