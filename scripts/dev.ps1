$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $PSScriptRoot

$Backend = Start-Process -PassThru -NoNewWindow -WorkingDirectory "$RootDir/backend" `
    -FilePath "uv" -ArgumentList "run", "uvicorn", "main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"
$Frontend = Start-Process -PassThru -NoNewWindow -WorkingDirectory "$RootDir/frontend" `
    -FilePath "npm" -ArgumentList "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"

try {
    Wait-Process -Id $Backend.Id, $Frontend.Id
}
finally {
    Stop-Process -Id $Backend.Id, $Frontend.Id -ErrorAction SilentlyContinue
}