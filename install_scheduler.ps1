# Registrira Windows zadatak koji svakih 10 min pokrece "auto_publish.py tick" (skriveno, pythonw).
# Pokretanje: desni klik -> Run with PowerShell, ili: powershell -ExecutionPolicy Bypass -File install_scheduler.ps1
# Uklanjanje: Unregister-ScheduledTask -TaskName 'Maze Cults Auto Publish' -Confirm:$false
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyw = Join-Path (Split-Path (Get-Command python).Source) 'pythonw.exe'
$action = New-ScheduledTaskAction -Execute $pyw -Argument "`"$dir\auto_publish.py`" tick" -WorkingDirectory $dir
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes 10)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName 'Maze Cults Auto Publish' -Action $action -Trigger $trigger -Settings $settings `
    -Description 'Generira i objavljuje maze dizajne na Cults3D (auto_publish.py tick)' -Force | Out-Null
Get-ScheduledTask -TaskName 'Maze Cults Auto Publish' | Get-ScheduledTaskInfo | Format-List NextRunTime
Write-Host 'Zadatak registriran. Log: logs\auto_publish.log'
