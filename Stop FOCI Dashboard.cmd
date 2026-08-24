@echo off
powershell -NoProfile -ExecutionPolicy Bypass -Command "$exe = [IO.Path]::GetFullPath('%~dp0.venv\Scripts\python.exe'); Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq $exe -and $_.CommandLine -match 'foci_ble dashboard' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo FOCI Dashboard stopped.
