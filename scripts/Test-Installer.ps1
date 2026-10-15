param([Parameter(Mandatory=$true)][string]$Iscc, [Parameter(Mandatory=$true)][string]$TestRoot, [string]$ProjectRoot = '')
$ErrorActionPreference = 'Stop'
$root = if ($ProjectRoot) { [IO.Path]::GetFullPath($ProjectRoot) } else { Split-Path -Parent $PSScriptRoot }
$version = (Get-Content -LiteralPath (Join-Path $root 'VERSION') -Raw).Trim()
$TestRoot = [IO.Path]::GetFullPath($TestRoot)
if (Test-Path -LiteralPath $TestRoot) { throw 'Use a new empty test root to avoid modifying existing data.' }
New-Item -ItemType Directory -Path $TestRoot | Out-Null
$payload = Join-Path $root ('artifacts\ViewFilterManager-' + $version + '-Revit2026')
$installer = Join-Path $TestRoot ('ViewFilterManager-' + $version + '-Installer-Test.exe')
function Invoke-Checked([string]$Executable, [string]$Arguments, [bool]$Success = $true) {
 $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -PassThru -Wait -WindowStyle Hidden
 if ($Success -and $process.ExitCode -ne 0) { throw "Expected success; got $($process.ExitCode): $Executable" }
 if (-not $Success -and $process.ExitCode -eq 0) { throw "Expected refusal: $Executable" }
 return $process.ExitCode
}
& $Iscc ('/DTestRoot=' + $TestRoot) ('/DPayloadDir=' + $payload) ('/DOutputPath=' + $TestRoot) (Join-Path $root 'installer\ViewFilterManager.iss') | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Test installer compile failed.' }
$manifestPath = Join-Path $TestRoot 'Addins\ViewFilterManager.addin'
New-Item -ItemType Directory -Path (Split-Path -Parent $manifestPath) | Out-Null
[IO.File]::WriteAllText($manifestPath, '<foreign-application/>')
$baseArguments = '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-'
$null = Invoke-Checked $installer ($baseArguments + ' /LOG="' + (Join-Path $TestRoot 'foreign.log') + '"') $false
if ([IO.File]::ReadAllText($manifestPath) -ne '<foreign-application/>') { throw 'Foreign registration was modified.' }
Remove-Item -LiteralPath $manifestPath
$null = Invoke-Checked $installer ($baseArguments + ' /LOG="' + (Join-Path $TestRoot 'install.log') + '"')
$installed = Join-Path $TestRoot ('App\Versions\' + $version)
$manifest = [xml](Get-Content -LiteralPath $manifestPath -Raw)
if ($manifest.RevitAddIns.AddIn.FullClassName -ne 'ViewFilterManager.Addin.Application') { throw 'Incorrect registration class.' }
if ($manifest.RevitAddIns.AddIn.Assembly -ne (Join-Path $installed 'ViewFilterManager.Addin.dll')) { throw 'Incorrect registered assembly path.' }
$count = 0
foreach ($file in Get-ChildItem -LiteralPath $payload -File -Recurse) {
 $relative = $file.FullName.Substring($payload.Length).TrimStart('\')
 $target = Join-Path $installed $relative
 if ((Get-FileHash -LiteralPath $target).Hash -ne (Get-FileHash -LiteralPath $file.FullName).Hash) { throw "Payload mismatch: $relative" }
 $count++
}
$null = Invoke-Checked $installer ($baseArguments + ' /LOG="' + (Join-Path $TestRoot 'repair.log') + '"')
# Fixture-only installer validates the upgrade mechanism using the same known payload.
$next = '2.0.1'
& $Iscc ('/DAppVersion=' + $next) ('/DTestRoot=' + $TestRoot) ('/DPayloadDir=' + $payload) ('/DOutputPath=' + $TestRoot) (Join-Path $root 'installer\ViewFilterManager.iss') | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Upgrade fixture compile failed.' }
$upgrade = Join-Path $TestRoot ('ViewFilterManager-' + $next + '-Installer-Test.exe')
$null = Invoke-Checked $upgrade ($baseArguments + ' /LOG="' + (Join-Path $TestRoot 'upgrade.log') + '"')
if ((Get-Content -LiteralPath (Join-Path $TestRoot 'App\installed-version.txt') -Raw).Trim() -ne $next) { throw 'Upgrade record not updated.' }
if (-not (Test-Path -LiteralPath (Join-Path $installed 'ViewFilterManager.Addin.dll'))) { throw 'Previous version was not preserved.' }
$upgradedManifest = [IO.File]::ReadAllText($manifestPath)
if ($upgradedManifest -notmatch 'Versions\\2.0.1') { throw 'Upgrade did not switch manifest.' }
$null = Invoke-Checked $installer ($baseArguments + ' /LOG="' + (Join-Path $TestRoot 'downgrade.log') + '"') $false
if ([IO.File]::ReadAllText($manifestPath) -ne $upgradedManifest) { throw 'Blocked downgrade changed registration.' }
$uninstaller = Join-Path $TestRoot 'App\Setup\unins000.exe'
$null = Invoke-Checked $uninstaller ($baseArguments + ' /LOG="' + (Join-Path $TestRoot 'uninstall.log') + '"')
if (Test-Path -LiteralPath $manifestPath) { throw 'Registration remains after uninstall.' }
if (Test-Path -LiteralPath (Join-Path $installed 'ViewFilterManager.Addin.dll')) { throw 'Payload remains after uninstall.' }
if (Test-Path -LiteralPath (Join-Path $TestRoot 'App\Versions\2.0.1\ViewFilterManager.Addin.dll')) { throw 'Upgrade payload remains after uninstall.' }
Write-Output "Installer checks passed: foreign registration refusal, $count verified files, install, repair, upgrade, downgrade refusal, uninstall."
