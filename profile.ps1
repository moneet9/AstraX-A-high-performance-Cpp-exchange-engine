param(
    [string]$BuildDir = "build",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $BuildDir "profiling"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$orderBookBench = Join-Path $BuildDir "engine/bench/bench_order_book.exe"
$matchingBench = Join-Path $BuildDir "engine/bench/bench_matching.exe"

function Invoke-IfExists {
    param(
        [string]$Path,
        [scriptblock]$Action
    )

    if (Test-Path $Path) {
        & $Action
    }
}

$benchSummary = @()

Invoke-IfExists $orderBookBench {
    $jsonPath = Join-Path $OutputDir "bench_order_book.json"
    & $orderBookBench --benchmark_format=json --benchmark_out=$jsonPath | Out-Null
    $benchSummary += "order_book => $jsonPath"
}

Invoke-IfExists $matchingBench {
    $jsonPath = Join-Path $OutputDir "bench_matching.json"
    & $matchingBench --benchmark_format=json --benchmark_out=$jsonPath | Out-Null
    $benchSummary += "matching => $jsonPath"
}

Set-Content -Path (Join-Path $OutputDir "summary.txt") -Value ($benchSummary -join [Environment]::NewLine)
Write-Host "Benchmark reports written to $OutputDir"

