@echo off
setlocal
chcp 65001 >nul 2>&1
title Установка Majestic Text Helper
cd /d "%~dp0"

echo ==================================================
echo    УСТАНОВКА MAJESTIC TEXT HELPER
echo ==================================================
echo.

if not exist "MajesticTextHelper\MajesticTextHelper.exe" (
  echo [ОШИБКА] Папка MajesticTextHelper с программой не найдена
  echo рядом с этим файлом.
  echo.
  echo Скорее всего архив распакован не целиком.
  echo Распакуйте ВЕСЬ архив: правый клик по архиву -
  echo "Извлечь всё..." - "Извлечь", затем запустите
  echo УСТАНОВИТЬ.bat из распакованной папки.
  echo.
  pause
  exit /b 1
)

set "DEST=%LOCALAPPDATA%\MajesticTextHelper"

echo [1/4] Закрываю запущенную копию программы (если была)...
taskkill /f /im MajesticTextHelper.exe >nul 2>&1

echo [2/4] Копирую программу...
echo       Куда: %DEST%
if not exist "%DEST%" mkdir "%DEST%"
xcopy "MajesticTextHelper" "%DEST%\" /e /i /y /q >nul
if errorlevel 1 (
  echo [ОШИБКА] Не удалось скопировать файлы.
  echo Проверьте, что антивирус не блокирует, и запустите
  echo установку ещё раз.
  pause
  exit /b 1
)

echo [3/4] Создаю ярлыки ("Majestic Text Helper")...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Majestic Text Helper.lnk'); $s.TargetPath=$env:DEST+'\MajesticTextHelper.exe'; $s.WorkingDirectory=$env:DEST; $s.Save()" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut([Environment]::GetFolderPath('ApplicationData')+'\Microsoft\Windows\Start Menu\Programs\Majestic Text Helper.lnk'); $s.TargetPath=$env:DEST+'\MajesticTextHelper.exe'; $s.WorkingDirectory=$env:DEST; $s.Save()" >nul 2>&1

echo [4/4] Запускаю программу...
start "" "%DEST%\MajesticTextHelper.exe"

echo.
echo ==================================================
echo    ГОТОВО!
echo.
echo    * Ярлык "Majestic Text Helper" - на рабочем столе.
echo    * При первом запуске Windows спросит права
echo      администратора - жмите "ДА".
echo    * Синее окно "Windows защитила ваш ПК"?
echo      Жмите "Подробнее" - "Выполнить в любом случае".
echo    * Обновление: запустите этот файл ещё раз -
echo      ваши настройки НЕ потеряются.
echo    * Удаление: удалите ярлык с рабочего стола и папку
echo      %DEST%
echo.
echo    Подробная инструкция - в файле ПРОЧТИ_МЕНЯ.txt
echo ==================================================
echo.
echo Это окно можно закрыть.
pause >nul
endlocal
