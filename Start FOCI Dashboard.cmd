@echo off
setlocal
set "FOCI_PROJECT=%~dp0"
set "FOCI_URL=http://127.0.0.1:8765/"

powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ^
  "$project = $env:FOCI_PROJECT; $url = $env:FOCI_URL; $python = Join-Path $project '.venv\Scripts\python.exe'; $ready = $false; try { $null = Invoke-RestMethod -Uri ($url + 'api/status') -TimeoutSec 1; $ready = $true } catch {}; if (-not $ready) { Start-Process -FilePath $python -ArgumentList @('-u','-m','foci_ble','dashboard','--no-open') -WorkingDirectory $project -WindowStyle Hidden; for ($i = 0; $i -lt 40 -and -not $ready; $i++) { Start-Sleep -Milliseconds 250; try { $null = Invoke-RestMethod -Uri ($url + 'api/status') -TimeoutSec 1; $ready = $true } catch {} } }; if ($ready) { Start-Process $url } else { Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('The FOCI dashboard could not be started.','FOCI Desktop') | Out-Null; exit 1 }"

endlocal
