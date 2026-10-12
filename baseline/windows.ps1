# Build the frozen application and separate reference drivers.
# No production files are read from the infrastructure checkout.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Native([string]$Exe, [string[]]$Arguments) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Exe failed with exit code $LASTEXITCODE"
    }
}

function Capture([string]$Exe, [string[]]$Arguments) {
    $result = & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Exe failed with exit code $LASTEXITCODE"
    }
    return ($result | Out-String).Trim()
}

$source = 'a0b4563a076e336863f743ec92c1ee8221f5aba6'
$sourceTree = '2759fa354d66adbc342c882d8f0faa390699bed4'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

if (!$env:RUNNER_TEMP) { throw 'RUNNER_TEMP is required' }
if (!$env:BASELINE_PYTHON -or !$env:BASELINE_BASE_PYTHON) {
    throw 'The verified Python helper environment is required'
}

$work = Join-Path $env:RUNNER_TEMP 'trdrop-reference'
$artifact = Join-Path $repo 'reference-artifact'
$python = $env:BASELINE_PYTHON
$basePython = $env:BASELINE_BASE_PYTHON

if (Test-Path -LiteralPath $work) {
    throw "Refusing to reuse build directory: $work"
}
if (Test-Path -LiteralPath $artifact) {
    throw "Refusing to reuse artifact directory: $artifact"
}
New-Item -ItemType Directory -Path $artifact | Out-Null

$pythonInfo = Capture $python @(
    '-I', '-c',
    'import json,platform,struct,sys; print(json.dumps({"version":platform.python_version(),"bits":struct.calcsize("P")*8,"executable":sys.executable,"prefix":sys.prefix,"base_prefix":sys.base_prefix,"implementation":platform.python_implementation()}))'
) | ConvertFrom-Json
if ($pythonInfo.version -ne '3.13.15' -or $pythonInfo.bits -ne 64) {
    throw 'Expected Python 3.13.15 x64'
}
if ($pythonInfo.prefix -eq $pythonInfo.base_prefix) {
    throw 'Python helpers must run in a virtual environment'
}

$selectedPython = Get-Content -LiteralPath $env:BASELINE_PYTHON_PROVENANCE -Raw |
    ConvertFrom-Json
$baseHash = (Get-FileHash -LiteralPath $basePython -Algorithm SHA256).
    Hash.ToLowerInvariant()
if ($selectedPython.version -ne '3.13.15' -or
    $selectedPython.bits -ne 64 -or
    $selectedPython.executable -ne $basePython -or
    $selectedPython.sha256 -cne $baseHash) {
    throw 'Selected interpreter provenance mismatch'
}

# Check that the Qt action retained the complete locked package inventory.
$lock = Join-Path $PSScriptRoot 'python-win64.lock'
$expectedPackages = @{}
foreach ($line in Get-Content -LiteralPath $lock) {
    if (!$line.Trim() -or $line.TrimStart().StartsWith('#')) { continue }
    if ($line -notmatch '^([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+) --hash=sha256:[0-9a-f]{64}$') {
        throw "Invalid lock entry: $line"
    }
    $name = ($Matches[1].ToLowerInvariant() -replace '[-_.]+', '-')
    if ($expectedPackages.ContainsKey($name)) {
        throw "Duplicate lock entry: $name"
    }
    $expectedPackages[$name] = $Matches[2]
}

$installedPackages = Capture $python @('-m', 'pip', 'list', '--format=json') |
    ConvertFrom-Json
if (@($installedPackages).Count -ne $expectedPackages.Count) {
    throw 'Installed Python package count differs from lock'
}
foreach ($package in $installedPackages) {
    $name = ($package.name.ToLowerInvariant() -replace '[-_.]+', '-')
    if (!$expectedPackages.ContainsKey($name) -or
        $expectedPackages[$name] -cne $package.version) {
        throw "Installed Python package differs from lock: $name"
    }
}
Native $python @('-m', 'pip', 'check')

Copy-Item -LiteralPath $lock -Destination $artifact
Copy-Item -LiteralPath $env:BASELINE_PYTHON_PROVENANCE -Destination $artifact
Copy-Item -LiteralPath $env:BASELINE_PYTHON_INSTALL_REPORT -Destination $artifact

$qt = $env:QT_ROOT_DIR
if (!$qt -or !$env:IQTA_TOOLS) {
    throw 'Qt action did not export QT_ROOT_DIR and IQTA_TOOLS'
}
$mingw = Join-Path $env:IQTA_TOOLS 'mingw810_64/bin'
$qmake = Join-Path $qt 'bin/qmake.exe'
$compiler = Join-Path $mingw 'g++.exe'
$make = Join-Path $mingw 'mingw32-make.exe'

if (!(Test-Path -LiteralPath $compiler -PathType Leaf)) {
    throw "Pinned MinGW kit not found: $mingw"
}
$env:PATH = "$mingw;$qt/bin;$env:PATH"

$gcc = Capture $compiler @('-dumpfullversion')
$target = Capture $compiler @('-dumpmachine')
$qtver = Capture $qmake @('-query', 'QT_VERSION')
if ($gcc -ne '8.1.0') { throw "Unexpected compiler: $gcc" }
if ($target -ne 'x86_64-w64-mingw32') {
    throw "Unexpected compiler target: $target"
}
if ($qtver -ne '5.15.2') { throw "Unexpected Qt: $qtver" }

$historicalUrl = 'https://github.com/illusion0001/opencv-build/releases/download/4.5.1/opencv-4.5.1.7z'
$canonicalUrl = 'https://github.com/illusionyy/opencv-build/releases/download/4.5.1/opencv-4.5.1.7z'
$expectedHash = '0e92740a93f2575036c1b3e07da6e7ed4d81e84882deb406c435d482b5d621f6'
$expectedSize = 167306384
$archive = Join-Path $env:RUNNER_TEMP 'opencv-4.5.1.7z'

# Inspect the first response only; do not print signed asset URLs.
$headers = Capture 'curl.exe' @(
    '--fail', '--silent', '--show-error', '--head',
    '--proto', '=https', '--max-redirs', '0', $historicalUrl
)
if ($headers -notmatch '(?m)^HTTP/\S+\s+301\b') {
    throw 'Historical OpenCV URL no longer returns the reviewed HTTP 301'
}
$location = [regex]::Match(
    $headers, '(?im)^location:\s*([^\r\n]+)'
)
if (!$location.Success -or
    $location.Groups[1].Value.Trim() -cne $canonicalUrl) {
    throw 'Historical OpenCV redirect target differs from the reviewed URL'
}

Native 'curl.exe' @(
    '--fail', '--location', '--silent', '--show-error',
    '--proto', '=https', '--proto-redir', '=https',
    '--retry', '3', '--max-redirs', '5',
    $historicalUrl, '--output', $archive
)

$archiveSize = (Get-Item -LiteralPath $archive).Length
$archiveHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).
    Hash.ToLowerInvariant()
if ($archiveSize -ne $expectedSize) {
    throw "OpenCV archive size mismatch: $archiveSize"
}
if ($archiveHash -cne $expectedHash) {
    throw 'OpenCV archive hash mismatch'
}

$env:OpenCV_DIR = Join-Path $env:RUNNER_TEMP 'opencv-4.5.1'
if (Test-Path -LiteralPath $env:OpenCV_DIR) {
    throw 'Refusing to reuse an OpenCV extraction'
}
Native '7z' @('x', $archive, "-o$env:RUNNER_TEMP", '-y')

$prepare = Join-Path $PSScriptRoot 'prepare.py'
Native $python @($prepare, $repo, $work)
Native $python @($prepare, '--verify', $repo, $work)

$manifestPath = Join-Path $work 'source-manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw |
    ConvertFrom-Json
if ($manifest.source_sha -cne $source -or
    $manifest.source_tree -cne $sourceTree) {
    throw 'Frozen-source manifest does not identify the required commit/tree'
}
Copy-Item -LiteralPath $manifestPath -Destination $artifact

$toolchain = [ordered]@{
    source_sha = $source
    source_tree = $sourceTree
    infrastructure_sha = $env:GITHUB_SHA
    run_id = $env:GITHUB_RUN_ID
    run_attempt = $env:GITHUB_RUN_ATTEMPT
    runner_image = $env:ImageOS
    runner_image_version = $env:ImageVersion
    python_selected = $selectedPython
    python_helper = $pythonInfo
    python_helper_executable_sha256 = (
        Get-FileHash -LiteralPath $python -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    python_lock_sha256 = (
        Get-FileHash -LiteralPath $lock -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    python_packages = $installedPackages
    python_install_report = 'python-install-report.json'
    python_package_inventory_matches_lock = $true
    qt = $qtver
    gcc = $gcc
    compiler_target = $target
    gcc_full = Capture $compiler @('--version')
    qmake = Capture $qmake @('-query')
    git = Capture 'git' @('--version')
    curl = Capture 'curl.exe' @('--version')
    seven_zip = Capture '7z' @('i')
    opencv = '4.5.1'
    opencv_dependency = [ordered]@{
        historical_url = $historicalUrl
        canonical_url = $canonicalUrl
        redirect_status = 301
        redirect_verified_utc = [DateTime]::UtcNow.ToString('o')
        release_id = 56244497
        asset_id = 52959360
        archive_sha256 = $archiveHash
        archive_size_bytes = $archiveSize
        provenance_limit = 'Original CI had no digest; historical immutability is unproven'
    }
    actions = [ordered]@{
        checkout = 'de0fac2e4500dabe0009e67214ff5f5447ce83dd'
        setup_python = '5fda3b95a4ea91299a34e894583c3862153e4b97'
        install_qt_subaction = '48d3ad6db93f3627c8ee7a0454bc6f3744f7e730'
        upload_artifact = '043fb46d1a93c77aae656e7c1c64a875d1fc6a0a'
    }
    build = 'Release C++11 qmake win32-g++ -fopenmp; no fast-math or ISA overrides'
    cpu = @(Get-CimInstance Win32_Processor |
        Select-Object Name, NumberOfCores, NumberOfLogicalProcessors)
    os = Get-CimInstance Win32_OperatingSystem |
        Select-Object Caption, Version, BuildNumber
}
$toolchain | ConvertTo-Json -Depth 10 |
    Set-Content "$artifact/toolchain.json" -Encoding utf8

$bin = Join-Path $artifact 'bin'
New-Item -ItemType Directory -Path $bin | Out-Null
$appBuild = Join-Path $work 'app-build'
New-Item -ItemType Directory -Path $appBuild | Out-Null

Push-Location $appBuild
try {
    Native $qmake @(
        "$work/original/trdrop/trdrop.pro",
        '-spec', 'win32-g++',
        'CONFIG+=release', 'CONFIG+=qtquickcompiler'
    )
    Native $make @('-f', 'Makefile.Release', '-j2')
    Copy-Item 'release/trdrop.exe' "$bin/trdrop-original.exe"
} finally {
    Pop-Location
}

$variants = @(
    @{ name = 'oracle'; profile = '0'; trace = '1' },
    @{ name = 'observed-profile'; profile = '1'; trace = '1' },
    @{ name = 'profile'; profile = '1'; trace = '0' }
)
foreach ($variant in $variants) {
    $build = Join-Path $work $variant.name
    New-Item -ItemType Directory -Path $build | Out-Null
    Push-Location $build
    try {
        Native $qmake @(
            "$repo/baseline/reference.pro",
            '-spec', 'win32-g++',
            "ORACLE=$work/observed",
            "PROFILE=$($variant.profile)",
            "TRACE=$($variant.trace)"
        )
        Native $make @('-f', 'Makefile.Release', '-j2')
        Copy-Item 'release/trdrop-reference.exe' "$bin/$($variant.name).exe"
    } finally {
        Pop-Location
    }
}

Copy-Item "$env:OpenCV_DIR/build_64/install/x64/mingw/bin/*.dll" $bin
foreach ($dll in @(
    'libgcc_s_seh-1.dll',
    'libstdc++-6.dll',
    'libwinpthread-1.dll',
    'libgomp-1.dll'
)) {
    Copy-Item "$mingw/$dll" $bin
}
Native "$qt/bin/windeployqt.exe" @(
    '--release',
    '--qmldir', "$work/original/trdrop",
    "$bin/trdrop-original.exe"
)

$env:PATH = "$bin;$env:PATH"
$env:QT_QPA_PLATFORM = 'offscreen'
$env:OMP_NUM_THREADS = '1'
$env:OMP_DYNAMIC = 'FALSE'
$env:OMP_NESTED = 'FALSE'
$env:OMP_MAX_ACTIVE_LEVELS = '1'

$runner = Join-Path $PSScriptRoot 'run.py'
Native $python @(
    '-m', 'unittest', 'discover',
    '-s', "$repo/tests/baseline", '-v'
)
Native $python @("$PSScriptRoot/fixtures.py", "$artifact/fixtures")
Native $python @(
    $runner, 'capture', "$bin/oracle.exe",
    "$artifact/fixtures", "$artifact/reference"
)
Native $python @(
    $runner, 'capture', "$bin/oracle.exe",
    "$artifact/fixtures", "$artifact/repeat"
)
Native $python @(
    $runner, 'compare', "$artifact/reference", "$artifact/repeat"
)
Native $python @(
    $runner, 'capture', "$bin/observed-profile.exe",
    "$artifact/fixtures", "$artifact/observed-profile"
)
Native $python @(
    $runner, 'compare',
    "$artifact/reference", "$artifact/observed-profile"
)
Native $python @(
    $runner, 'capture', "$bin/oracle.exe",
    "$artifact/fixtures", "$artifact/hazards", '--hazards'
)
Native $python @(
    $runner, 'capture', "$bin/profile.exe",
    "$artifact/fixtures", "$artifact/lean-profile",
    '--no-trace', '--only', 'pipeline_csv'
)

# This source video is an already-rendered demonstration, not raw truth.
Native "$bin/oracle.exe" @(
    '--video', "$work/original/videos/2019-07-02-first-fps-analysis.mp4",
    '--output', "$artifact/decode-smoke",
    '--limit', '10'
)

# Recheck the independently verified frozen files before declaring success.
Native $python @($prepare, '--verify', $repo, $work)

@{
    status = 'build-and-driver-tests-passed'
    gui_interactive_tests = 'not run'
    source_sha = $source
    source_tree = $sourceTree
    infrastructure_sha = $env:GITHUB_SHA
} | ConvertTo-Json |
    Set-Content "$artifact/STATUS.json" -Encoding utf8

# hashes.json deliberately excludes itself.
Get-ChildItem -LiteralPath $artifact -Recurse -File |
    Sort-Object FullName |
    ForEach-Object {
        [PSCustomObject]@{
            path = $_.FullName.Substring($artifact.Length + 1)
            sha256 = (
                Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
            ).Hash.ToLowerInvariant()
        }
    } | ConvertTo-Json -Depth 4 |
    Set-Content "$artifact/hashes.json" -Encoding utf8

if ($env:GITHUB_STEP_SUMMARY) {
    "Frozen Windows x64 application and reference drivers built. Deterministic repeat and profiling-on/off trace comparisons passed. Interactive QML/video scheduling not tested. Source: $source." >> $env:GITHUB_STEP_SUMMARY
    Get-Content "$artifact/lean-profile/pipeline_csv/timings.json" >> $env:GITHUB_STEP_SUMMARY
}
