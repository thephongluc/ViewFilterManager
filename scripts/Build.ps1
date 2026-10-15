param([string]$Configuration = 'Release', [string]$RevitDir = '', [string]$Iscc = '', [switch]$NoInstaller, [switch]$SkipTests, [string]$ProjectRoot = '')
$ErrorActionPreference = 'Stop'
$env:MSBuildEnableWorkloadResolver = 'false'
$env:DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE = 'true'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$root = if ($ProjectRoot) { [IO.Path]::GetFullPath($ProjectRoot) } else { Split-Path -Parent $PSScriptRoot }
$version = (Get-Content -LiteralPath (Join-Path $root 'VERSION') -Raw).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw 'VERSION must be MAJOR.MINOR.PATCH.' }
[IO.File]::WriteAllText((Join-Path $root 'runtime\VERSION'), $version + "`n", (New-Object Text.UTF8Encoding($false)))
$arguments = @('-c', $Configuration, '-v', 'minimal')
if ($RevitDir) { $arguments += ('-p:RevitDir=' + $RevitDir) }
foreach ($project in @('src\ViewFilterManager.Addin\ViewFilterManager.Addin.csproj', 'src\ViewFilterManager.Runtime\ViewFilterManager.Runtime.csproj', 'tests\HostSmoke\HostSmoke.csproj')) {
    & dotnet build (Join-Path $root $project) @arguments
    if ($LASTEXITCODE -ne 0) { throw "Build failed: $project" }
}
$artifacts = Join-Path $root 'artifacts'
$stage = Join-Path $artifacts ('ViewFilterManager-' + $version + '-Revit2026')
if (-not [IO.Path]::GetFullPath($stage).StartsWith([IO.Path]::GetFullPath($artifacts) + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid artifact stage path.' }
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null
$runtimeBin = Join-Path $root ('src\ViewFilterManager.Runtime\bin\' + $Configuration + '\net8.0-windows')
Copy-Item -Path (Join-Path $runtimeBin '*') -Destination $stage -Recurse -Force
Copy-Item -LiteralPath (Join-Path $root ('src\ViewFilterManager.Addin\bin\' + $Configuration + '\net8.0-windows\ViewFilterManager.Addin.dll')) -Destination $stage -Force
$contentSource = Join-Path $root 'runtime'
$contentStage = Join-Path $stage 'Content'
foreach ($file in Get-ChildItem -LiteralPath $contentSource -File -Recurse) {
    if ($file.FullName -match '\\__pycache__\\' -or $file.Extension -eq '.pyc') { continue }
    $relative = $file.FullName.Substring($contentSource.Length).TrimStart('\')
    $target = Join-Path $contentStage $relative
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    Copy-Item -LiteralPath $file.FullName -Destination $target -Force
}
foreach ($name in @('README.md','CHANGELOG.md','THIRD-PARTY-NOTICES.md','VERSION')) { Copy-Item -LiteralPath (Join-Path $root $name) -Destination $stage -Force }
Copy-Item -LiteralPath (Join-Path $root 'licenses') -Destination $stage -Recurse -Force
Copy-Item -LiteralPath (Join-Path $root 'docs') -Destination $stage -Recurse -Force
if (Test-Path -LiteralPath (Join-Path $stage 'RevitAPI.dll')) { throw 'Autodesk API DLL must never be packaged.' }
if (Test-Path -LiteralPath (Join-Path $stage 'RevitAPIUI.dll')) { throw 'Autodesk API UI DLL must never be packaged.' }
if (-not (Test-Path -LiteralPath (Join-Path $stage 'lib\os.py'))) { throw 'Embedded standard library missing.' }
Copy-Item -LiteralPath (Join-Path $root 'installer\ViewFilterManager.addin.example') -Destination $stage -Force
if (-not $SkipTests) {
    & python (Join-Path $root 'tests\test_logic.py')
    if ($LASTEXITCODE -ne 0) { throw 'Logic checks failed.' }
    $testBin = Join-Path $root ('tests\HostSmoke\bin\' + $Configuration + '\net8.0-windows')
    if (-not (Test-Path -LiteralPath (Join-Path $testBin 'lib'))) { Copy-Item -LiteralPath (Join-Path $runtimeBin 'lib') -Destination $testBin -Recurse -Force }
    & dotnet (Join-Path $testBin 'HostSmoke.dll') (Join-Path $root 'runtime') (Join-Path $artifacts 'preview')
    if ($LASTEXITCODE -ne 0) { throw 'Embedded engine / WPF checks failed.' }
}
if (-not $NoInstaller) {
    if (-not $Iscc) {
        $found = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($found) { $Iscc = $found.Source } else { $Iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
    }
    if (-not (Test-Path -LiteralPath $Iscc)) { throw 'Inno Setup 6 compiler not found. Pass -Iscc <path>.' }
    & $Iscc ('/DPayloadDir=' + $stage) ('/DOutputPath=' + $artifacts) (Join-Path $root 'installer\ViewFilterManager.iss')
    if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
}
$zip = Join-Path $artifacts ('ViewFilterManager-' + $version + '-Revit2026-portable.zip')
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip -Force
$checksums = Get-ChildItem -LiteralPath $artifacts -File | Where-Object { $_.Name -like ('*' + $version + '*') -and $_.Extension -in @('.exe','.zip') } | Sort-Object Name | ForEach-Object { (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() + '  ' + $_.Name }
[IO.File]::WriteAllLines((Join-Path $artifacts 'SHA256SUMS.txt'), $checksums, (New-Object Text.UTF8Encoding($false)))
Write-Output "Release $version ready: $artifacts"
