@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Majestic Text Helper - сборка установщика (Inno Setup)
set "PYTHONUTF8=1"
echo === Majestic Text Helper: сборка установщика Setup-EXE (v3.12.0) ===
echo.
cd /d "%~dp0"

REM --- Что делает этот файл: ---
REM  1) ставит зависимости (PySide6, keyboard, PyInstaller);
REM  2) собирает программу через PyInstaller (majestic_helper.spec);
REM  3) находит компилятор Inno Setup 6 (ISCC.exe);
REM  4) читает версию из app\__init__.py;
REM  5) собирает ОДИН файл: release\MajesticTextHelper-Setup-<версия>.exe —
REM     ЭТОТ ФАЙЛ и рассылаем сотрудникам вместо ZIP.
REM
REM  Если Inno Setup не установлен: скачайте с https://jrsoftware.org/isdl.php
REM  (обычный "innosetup-6....exe", стандартная установка), затем запустите
REM  этот bat ещё раз.

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
echo [3/5] Поиск компилятора Inno Setup 6 (ISCC.exe)...
set "ISCC="
for /f "delims=" %%i in ('where iscc 2^>nul') do if not defined ISCC set "ISCC=%%i"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
  echo [ОШИБКА] Inno Setup 6 не найден.
  echo.
  echo Установите его ОДИН раз:
  echo   1. Откройте https://jrsoftware.org/isdl.php
  echo   2. Скачайте innosetup-6.x.x.exe (обычная установка, всё "Далее").
  echo   3. Запустите build_installer.bat ещё раз.
  echo.
  pause
  exit /b 1
)
echo Найден компилятор: %ISCC%

echo.
echo [4/5] Определяю версию программы...
set "VER="
for /f "tokens=2 delims== " %%a in ('findstr /b /c:"APP_VERSION" app\__init__.py') do set "VER=%%a"
set VER=%VER:"=%
if "%VER%"=="" set "VER=3.12.0"
echo Версия: %VER%

echo.
echo [5/5] Сборка установщика (Inno Setup)...
if not exist "release" mkdir "release"
"%ISCC%" /DAPP_VERSION=%VER% "installer\majestic_helper.iss"
if errorlevel 1 (
  echo [ОШИБКА] Inno Setup не смог собрать установщик.
  echo Пришлите разработчику текст ошибки сверху.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo  ГОТОВО!
echo.
echo  УСТАНОВЩИК ДЛЯ СОТРУДНИКОВ (ОДИН ФАЙЛ):
echo    release\MajesticTextHelper-Setup-%VER%.exe
echo.
echo  Как пользоваться:
echo    1. Перешлите этот EXE сотрудникам (Discord / Telegram).
echo    2. Сотрудник запускает его двойным кликом - мастер
echo       установки всё сделает сам: программа встанет,
echo       ярлык появится на рабочем столе.
echo    3. Права администратора установщику НЕ нужны.
echo.
echo  Обновление: просто соберите новую версию этим файлом и
echo  разошлите новый Setup-EXE - он обновит программу ПОВЕРХ
echo  старой, все фразы и настройки сотрудников сохранятся.
echo.
echo  Удаление: Параметры Windows - "Приложения" -
echo  "Majestic Text Helper" - "Удалить".
echo ============================================================
pause
endlocal
