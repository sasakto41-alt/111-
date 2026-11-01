; ============================================================
;  Majestic Text Helper — установщик Inno Setup 6
;
;  Сборка: build_installer.bat (рекомендуется) или вручную:
;    ISCC.exe /DAPP_VERSION=3.12.0 installer\majestic_helper.iss
;  Результат: release\MajesticTextHelper-Setup-<версия>.exe
;  ОДИН файл — его и рассылаем сотрудникам.
;
;  Что делает установщик:
;   * ставит программу в %LOCALAPPDATA%\MajesticTextHelper —
;     ТОТ ЖЕ путь, что у старого УСТАНОВИТЬ.bat, поэтому обновление
;     поверх старой установки ложится ровно в то же место;
;   * НЕ требует прав администратора на установку (права спросит
;     сама программа при запуске — они ей нужны для хоткеев);
;   * создаёт ярлык «Majestic Text Helper» на рабочем столе
;     и в меню «Пуск»;
;   * по галочке — автозапуск вместе с Windows (по умолчанию выкл.);
;   * папка data\ (фразы, настройки, скриншоты) в пакет НЕ входит:
;     установка, обновление и удаление её не трогают.
; ============================================================

#ifndef APP_VERSION
  #define APP_VERSION "3.12.0"
#endif

#define MyAppName "Majestic Text Helper"
#define MyAppExe "MajesticTextHelper.exe"

[Setup]
; Стабильный AppId: Windows считает все версии одной программой
; (обновление поверх, сохранение настроек, корректное удаление).
AppId={{9C4F2B7A-6D1E-4A58-B3E9-0F2D8C7A15B4}
AppName={#MyAppName}
AppVersion={#APP_VERSION}
AppVerName={#MyAppName} {#APP_VERSION}
AppPublisher=Majestic Text Helper
AppPublisherURL=https://github.com/sasakto41-alt/111-
; Тот же путь, что использовал УСТАНОВИТЬ.bat из v3.9.0:
DefaultDirName={localappdata}\MajesticTextHelper
UsePreviousAppDir=yes
; Не пугаем сотрудника предупреждением при обновлении поверх:
DirExistsWarning=no
DisableProgramGroupPage=yes
; Установка БЕЗ прав администратора:
PrivilegesRequired=lowest
OutputDir=..\release
OutputBaseFilename=MajesticTextHelper-Setup-{#APP_VERSION}
SetupIconFile=..\assets\icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExe}
; Программа висит в трее — при обновлении предложим её закрыть:
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
; Ярлык на рабочем столе — включён по умолчанию:
Name: "desktopicon"; Description: "Ярлык на рабочем столе"; \
    GroupDescription: "Дополнительные значки:"; Flags: checkedonce
; Автозапуск с Windows — по умолчанию ВЫКЛЮЧЕН:
Name: "autostart"; \
    Description: "Запускать Majestic Text Helper вместе с Windows"; \
    GroupDescription: "Дополнительные значки:"; Flags: unchecked

[Files]
; Вся папка программы из PyInstaller (exe + _internal + assets).
; Папки data в сборке НЕТ — пользовательские фразы и скриншоты
; установщик физически не может перезаписать или удалить.
Source: "..\dist\MajesticTextHelper\*"; \
    DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; \
    WorkingDir: "{app}"
Name: "{group}\Удалить Majestic Text Helper"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; \
    WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; \
    WorkingDir: "{app}"; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"; \
    Description: "Запустить Majestic Text Helper"; \
    Flags: nowait postinstall skipifsilent

; [UninstallRun] намеренно нет: при удалении программы папка data\
; (фразы, настройки, скриншоты) ОСТАЁТСЯ на месте.
