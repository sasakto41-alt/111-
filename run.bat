@echo off
chcp 65001 >nul
title Majestic Text Helper - запуск без сборки
echo === Majestic Text Helper: запуск из исходников ===
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
  echo [ОШИБКА] Python не найден. Установите Python 3.10+ с python.org
  echo и при установке отметьте галочку "Add Python to PATH".
  pause
  exit /b 1
)

echo Проверяем зависимости (первый раз может занять минуту)...
python -m pip show PySide6 >nul 2>&1
if errorlevel 1 python -m pip install PySide6 keyboard

echo Запуск...
python main.py

if errorlevel 1 (
  echo.
  echo [ОШИБКА] Программа завершилась аварийно.
  if exist data\error.log (
    echo Отчёт об ошибке сохранён в файле: data\error.log
    echo Пришлите его содержимое разработчику.
  )
  pause
)
