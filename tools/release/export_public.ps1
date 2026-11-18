<#
.SYNOPSIS
  Exports the current HEAD as a fresh, single-commit repository for public release.

.DESCRIPTION
  The private repository and its history are NOT modified. Only tracked files of HEAD are exported
  (no .venv, build/, logs). Before exporting, all tracked files are scanned for private data
  (Windows user name, the private git e-mail and extra patterns); the export aborts on any hit.
  Nothing is pushed - create the public remote and push manually afterwards.
  Keep this file ASCII-only: Windows PowerShell 5.1 reads BOM-less UTF-8 as ANSI.

.EXAMPLE
  .\tools\release\export_public.ps1 -Destination C:\src\SetWhichGPU `
      -AuthorName "Your Name" -AuthorEmail "12345+you@users.noreply.github.com"
#>
param(
    [Parameter(Mandatory = $true)][string]$Destination,
    [Parameter(Mandatory = $true)][string]$AuthorName,
    [Parameter(Mandatory = $true)][string]$AuthorEmail,
    [string[]]$ExtraDenyPatterns = @(),
    [string]$Message = "Initial public release"
)
$ErrorActionPreference = "Stop"
$repo = (git rev-parse --show-toplevel).Trim()
Set-Location $repo

# 1) Clean working tree only - the export must match a commit.
if (git status --porcelain) { throw "Working tree is not clean. Commit or stash first." }

# 2) Destination must be new or empty.
if ((Test-Path $Destination) -and (Get-ChildItem $Destination -Force | Select-Object -First 1)) {
    throw "Destination '$Destination' is not empty."
}

# 3) Privacy scan of tracked files.
#    E-mails of this repo and of the global git config are private unless used as AuthorEmail.
#    The Windows user/computer name is private; if it equals the public AuthorName (e.g. the GitHub
#    user name), only its path forms are blocked so links like github.com/<name>/... stay possible.
$emails = @((git config --local user.email), (git config --global user.email)) | Where-Object { $_ -and $_ -ne $AuthorEmail }
$names = @()
foreach ($n in @($env:USERNAME, $env:COMPUTERNAME) | Where-Object { $_ } | Select-Object -Unique) {
    if ($n -ieq $AuthorName) { $names += @("Users\$n", "Users/$n", "\\$n\") } else { $names += $n }
}
$deny = @($names) + @($emails) + $ExtraDenyPatterns | Where-Object { $_ -and $_.Length -ge 4 } | Select-Object -Unique
if ($AuthorEmail -ieq (git config --local user.email)) { throw "AuthorEmail must not be the private e-mail. Use a GitHub noreply address." }
$hits = @()
foreach ($file in (git ls-files)) {
    if ($file -eq "uv.lock") { continue }
    foreach ($pattern in $deny) {
        $m = Select-String -Path (Join-Path $repo $file) -Pattern ([regex]::Escape($pattern)) -SimpleMatch:$false -ErrorAction SilentlyContinue
        if ($m) { $hits += $m | ForEach-Object { "{0}:{1}: matches '{2}'" -f $file, $_.LineNumber, $pattern } }
    }
}
if ($hits) { $hits | ForEach-Object { Write-Host $_ -ForegroundColor Red }; throw "Private data found - export aborted." }
Write-Host "Privacy scan passed ($($deny.Count) patterns)." -ForegroundColor Green

# 4) Export tracked files of HEAD.
$zip = Join-Path ([IO.Path]::GetTempPath()) ("gpucc-export-" + [guid]::NewGuid() + ".zip")
git archive --format=zip -o $zip HEAD
New-Item -ItemType Directory -Force $Destination | Out-Null
Expand-Archive -Path $zip -DestinationPath $Destination
Remove-Item $zip

# 5) Fresh repository with a single commit under the public identity.
Set-Location $Destination
git init -q -b main
git config user.name $AuthorName
git config user.email $AuthorEmail
git add -A
git commit -q -m $Message
Write-Host "Exported to $Destination as a single commit:" -ForegroundColor Green
git log --format="%h %an <%ae> %s"
Write-Host "Next: create the public repository, then 'git remote add origin <url>; git push -u origin main'."
