@echo off
chcp 65001 >nul
title Majestic Text Helper - сборка EXE
echo === Majestic Text Helper: сборка EXE (v3.2.0) ===
echo.

cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
  echo [ОШИБКА] Python не найден. Установите Python 3.10+ с python.org
  echo и при установке отметьте галочку "Add Python to PATH".
  pause
  exit /b 1
)

echo [1/3] Установка зависимостей...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ОШИБКА] Не удалось установить зависимости. Проверьте интернет.
  pause
  exit /b 1
)

echo.
echo [2/3] Сборка (PyInstaller, это занимает 1-3 минуты)...
python -m PyInstaller --clean -y majestic_helper.spec
if errorlevel 1 (
  echo [ОШИБКА] Сборка не удалась. Пришлите текст ошибки разработчику.
  pause
  exit /b 1
)

echo.
echo [3/3] Готово!
if exist dist\MajesticTextHelper.exe (
  echo ============================================================
  echo  УСПЕХ: dist\MajesticTextHelper.exe
  echo  Это portable-файл: положите его в любую папку и запускайте.
  echo  Данные хранятся рядом: data\data.json
  echo  При запуске Windows спросит права администратора — это
  echo  НУЖНО, чтобы хоткеи работали внутри игры.
  echo ============================================================
) else (
  echo [ОШИБКА] dist\MajesticTextHelper.exe не найден.
)
pause
