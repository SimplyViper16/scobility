param(
    [string]$Tourney = "itl2026"
)

$tourney = $Tourney.ToLower()
$tourneyUpper = $Tourney.ToUpper()
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Set-Location $scriptDir

function Log($msg) {
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
}

Log "=== Nightly update: $tourney ==="

Log "Step 1: Scraping data..."
python scobility_scrape.py $tourney
if ($LASTEXITCODE -ne 0) { Log "ERROR: scrape failed (exit $LASTEXITCODE)"; exit $LASTEXITCODE }

Log "Step 2: Processing scobility..."
python -c "import scobility; scobility.process(src='$tourney')"
if ($LASTEXITCODE -ne 0) { Log "ERROR: process failed (exit $LASTEXITCODE)"; exit $LASTEXITCODE }

Log "Step 3: Uploading to DB..."
python db_upload.py $tourneyUpper "..\scobility_$tourney.json"
if ($LASTEXITCODE -ne 0) { Log "ERROR: db_upload failed (exit $LASTEXITCODE)"; exit $LASTEXITCODE }

Log "=== Done! ==="
