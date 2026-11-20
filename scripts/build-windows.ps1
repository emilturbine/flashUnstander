param(
    [string]$InnoCompiler
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$originalPath = $env:PATH
Push-Location -LiteralPath $projectRoot
try {
    if ($InnoCompiler) {
        $InnoCompiler = (Get-Command $InnoCompiler -CommandType Application).Source
        $appVersion = & $projectPython -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])"
        if ($LASTEXITCODE -ne 0) { throw 'Could not read project version.' }
    }
    $pythonBase = & $projectPython -c "import sys; print(sys.base_prefix)"
    if ($LASTEXITCODE -ne 0) { throw 'Could not locate the base Python runtime.' }
    # Avoid pulling same-named DLLs from unrelated tools on the caller's PATH.
    $env:PATH = @(
        (Join-Path $env:SystemRoot 'System32')
        $env:SystemRoot
        (Split-Path -Parent $projectPython)
        $pythonBase
        (Join-Path $pythonBase 'Library\bin')
    ) -join ';'
    & $projectPython -m PyInstaller --clean --noconfirm --distpath dist --workpath build packaging/flashUnstander.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }

    if ($InnoCompiler) {
        & $InnoCompiler "/DAppVersion=$appVersion" packaging/flashUnstander.iss
        if ($LASTEXITCODE -ne 0) { throw 'Inno Setup build failed.' }
    }
}
finally {
    $env:PATH = $originalPath
    Pop-Location
}
