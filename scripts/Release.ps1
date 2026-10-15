param([switch]$Publish)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$version = (Get-Content -LiteralPath (Join-Path $root 'VERSION') -Raw).Trim()
Push-Location $root
try {
 if (git status --porcelain) { throw 'Commit all changes before tagging a release.' }
 $tag = 'v' + $version
 git tag -a $tag -m ('View Filter Manager ' + $version)
 if ($LASTEXITCODE -ne 0) { throw 'Tag creation failed.' }
 git push origin $tag
 if ($LASTEXITCODE -ne 0) { throw 'Tag push failed.' }
 Write-Output 'The workflow builds and validates the installer, then prepares a draft release.'
 if ($Publish) { Write-Output "After the workflow passes, publish using: gh release edit $tag --draft=false" }
} finally { Pop-Location }
