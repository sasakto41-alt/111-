@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Majestic Text Helper - сборка релиза для сотрудников
set "PYTHONUTF8=1"
echo === Majestic Text Helper: сборка релиза для рассылки (v3.9.0) ===
echo.
cd /d "%~dp0"

REM --- Что делает этот файл: ---
REM  1) ставит зависимости (PySide6, keyboard, PyInstaller);
REM  2) собирает программу через PyInstaller (majestic_helper.spec);
REM  3) читает версию из app\__init__.py;
REM  4) складывает в одну папку: программу + УСТАНОВИТЬ.bat + ПРОЧТИ_МЕНЯ.txt;
REM  5) упаковывает всё в release\MajesticTextHelper-v<версия>.zip —
REM     ЭТОТ ОДИН ФАЙЛ и нужно рассылать сотрудникам.

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
echo [1/5] Установка зависимостей (PySide6, keyboard, PyInstaller)...
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
echo [2/5] Сборка программы (PyInstaller, 1-3 минуты)...
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

if not exist "dist\MajesticTextHelper\MajesticTextHelper.exe" (
  echo [ОШИБКА] dist\MajesticTextHelper\MajesticTextHelper.exe не найден.
  echo Скорее всего антивирус удалил exe сразу после сборки.
  echo Добавьте папку проекта в исключения антивируса и соберите заново.
  pause
  exit /b 1
)

echo.
echo [3/5] Определяю версию программы...
set "VER="
for /f "tokens=2 delims== " %%a in ('findstr /b /c:"APP_VERSION" app\__init__.py') do set "VER=%%a"
set VER=%VER:"=%
if "%VER%"=="" set "VER=3.9.0"
echo Версия: %VER%

echo.
echo [4/5] Собираю пакет для сотрудников (программа + установщик + инструкция)...
if exist "release" rmdir /s /q "release"
mkdir "release\stage"
xcopy "dist\MajesticTextHelper" "release\stage\MajesticTextHelper\" /e /i /y /q >nul
copy /y "release_templates\УСТАНОВИТЬ.bat" "release\stage\" >nul
copy /y "release_templates\ПРОЧТИ_МЕНЯ.txt" "release\stage\" >nul
if not exist "release\stage\УСТАНОВИТЬ.bat" (
  echo [ОШИБКА] Не найден release_templates\УСТАНОВИТЬ.bat.
  echo Папка release_templates должна лежать рядом с make_release.bat.
  pause
  exit /b 1
)

echo.
echo [5/5] Упаковываю в ZIP (может занять минуту)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'release\stage\*' -DestinationPath 'release\MajesticTextHelper-v%VER%.zip' -Force"
if errorlevel 1 (
  echo [ВНИМАНИЕ] Автоупаковка не удалась - но все файлы уже собраны.
  echo Они лежат в папке release\stage - заархивируйте её вручную:
  echo правый клик по папке stage -^> "Отправить" -^> "Сжатая ZIP-папка".
  pause
  exit /b 1
)
rmdir /s /q "release\stage"

echo.
echo ============================================================
echo  ГОТОВО!
echo.
echo  ФАЙЛ ДЛЯ ОТПРАВКИ СОТРУДНИКАМ:
echo    release\MajesticTextHelper-v%VER%.zip
echo.
echo  Как пользоваться:
echo    1. Перешлите этот ZIP сотрудникам (Discord / Telegram / почта).
echo    2. Сотрудник распаковывает архив ЦЕЛИКОМ (правый клик -
echo       "Извлечь всё...").
echo    3. Запускает УСТАНОВИТЬ.bat - программа сама поставится,
echo       появится ярлык на рабочем столе.
echo.
echo  Обновление версии: просто соберите заново этим файлом и
echo  разошлите новый ZIP - сотрудники запустят УСТАНОВИТЬ.bat
echo  поверх старой версии, все их настройки сохранятся.
echo ============================================================
pause
endlocal
