# Majestic Text Helper - Windows OCR bridge (v3.10.0)
# Recognizes text on a PNG using the built-in Windows 10/11 OCR engine.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File ocr.ps1 <image.png> [-X 0 -Y 0 -W 0 -H 0]
# Output: recognized text on stdout, or "__OCR_NA__" if OCR engine is unavailable.
param(
    [Parameter(Mandatory = $true)][string]$ImagePath,
    [int]$X = 0,
    [int]$Y = 0,
    [int]$W = 0,
    [int]$H = 0
)
$ErrorActionPreference = "Stop"

function Await-WinRt($WinRtTask, $ResultType) {
    $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    })[0]
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    return $netTask.Result
}

try {
    if (-not (Test-Path -LiteralPath $ImagePath)) {
        Write-Output "__OCR_NA__"
        exit 1
    }

    # Optional crop (System.Drawing, Windows PowerShell 5.1)
    $target = $ImagePath
    if ($W -gt 0 -and $H -gt 0) {
        Add-Type -AssemblyName System.Drawing
        $src = [System.Drawing.Bitmap]::FromFile($ImagePath)
        $cx = [Math]::Max(0, [Math]::Min($X, $src.Width - 1))
        $cy = [Math]::Max(0, [Math]::Min($Y, $src.Height - 1))
        $cw = [Math]::Max(1, [Math]::Min($W, $src.Width - $cx))
        $ch = [Math]::Max(1, [Math]::Min($H, $src.Height - $cy))
        $rect = New-Object System.Drawing.Rectangle($cx, $cy, $cw, $ch)
        $crop = $src.Clone($rect, $src.PixelFormat)
        $tmpPath = [System.IO.Path]::Combine(
            [System.IO.Path]::GetTempPath(),
            ("mth_crop_" + [System.Guid]::NewGuid().ToString("N") + ".png"))
        $crop.Save($tmpPath, [System.Drawing.Imaging.ImageFormat]::Png)
        $crop.Dispose()
        $src.Dispose()
        $target = $tmpPath
    }

    # WinRT projections (Windows 10/11 built-in OCR)
    $null = [Windows.Storage.StorageFile, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Globalization.Language, Windows.Foundation, ContentType = WindowsRuntime]
    Add-Type -AssemblyName System.Runtime.WindowsRuntime

    $ocr = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if (-not $ocr) {
        $ocr = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage(
            (New-Object Windows.Globalization.Language("ru")))
    }
    if (-not $ocr) {
        Write-Output "__OCR_NA__"
        exit 1
    }

    $file = Await-WinRt ([Windows.Storage.StorageFile]::GetFileFromPathAsync($target)) `
        ([Windows.Storage.StorageFile])
    $stream = Await-WinRt ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) `
        ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await-WinRt ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) `
        ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await-WinRt ($decoder.GetSoftwareBitmapAsync()) `
        ([Windows.Graphics.Imaging.SoftwareBitmap])

    $result = Await-WinRt ($ocr.RecognizeAsync($bitmap)) `
        ([Windows.Media.Ocr.OcrResult])

    if ($target -ne $ImagePath) {
        Remove-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue
    }

    Write-Output $result.Text
    exit 0
}
catch {
    Write-Output "__OCR_NA__"
    exit 1
}
