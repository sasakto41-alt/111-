@echo off
chcp 65001 >nul
title Majestic Text Helper - сборка EXE
echo === Majestic Text Helper: сборка (v3.4.0) ===
echo.
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
  echo [ОШИБКА] Python не найден. Установите Python 3.10+ с python.org
  echo и при установке отметьте галочку "Add Python to PATH".
  pause
  exit /b 1
)

echo [1/4] Установка зависимостей...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ОШИБКА] Не удалось установить зависимости. Проверьте интернет.
  pause
  exit /b 1
)

echo.
echo [2/4] Сборка основной версии (PyInstaller, 1-3 минуты)...
python -m PyInstaller --clean -y majestic_helper.spec
if errorlevel 1 (
  echo [ОШИБКА] Сборка не удалась. Пришлите текст ошибки разработчику.
  pause
  exit /b 1
)

echo.
echo [3/4] Сборка диагностической версии (с окном консоли)...
python -m PyInstaller -y majestic_helper_debug.spec
if errorlevel 1 (
  echo [ВНИМАНИЕ] Диагностическая версия не собралась — основная всё равно готова.
)

echo.
echo [4/4] Готово!
if exist dist\MajesticTextHelper\MajesticTextHelper.exe (
  echo ============================================================
  echo  УСПЕХ!
  echo.
  echo  Программа:      dist\MajesticTextHelper\MajesticTextHelper.exe
  echo  Запускайте ИМЕННО его — из папки MajesticTextHelper.
  echo  Папку можно перенести куда угодно ЦЕЛИКОМ (вместе с _internal).
  echo.
  echo  Диагностика:    dist\MajesticTextHelper_debug\MajesticTextHelper_debug.exe
  echo  У неё видно чёрное окно консоли с ошибками — если основная
  echo  версия не открывается, запустите её и сфотографируйте текст.
  echo.
  echo  Данные хранятся рядом: data\data.json
  echo  При запуске Windows спросит права администратора — жмите "Да".
  echo ============================================================
) else (
  echo [ОШИБКА] dist\MajesticTextHelper\MajesticTextHelper.exe не найден.
)
pause
