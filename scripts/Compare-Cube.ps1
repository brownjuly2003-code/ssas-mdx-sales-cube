param([Parameter(Mandatory = $true)][string]$Server)
$ErrorActionPreference = 'Stop'
Import-Module SqlServer -ErrorAction Stop
$root = Split-Path -Parent $PSScriptRoot
$queries = Join-Path $root 'mdx'
# A new folder for every run: an answer left by an earlier run cannot be compared again.
$output = Join-Path $root ('reports/actual/' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$expected = Join-Path $root 'reports/expected.json'
if (-not (Test-Path -LiteralPath $expected -PathType Leaf)) {
    throw 'Generate reports/expected.json before comparing MDX queries.'
}
if (Test-Path -LiteralPath $output) { throw "$output already exists; start the comparison again." }
$files = @(Get-ChildItem -LiteralPath $queries -Filter '*.mdx' | Sort-Object Name)
$names = @((Get-Content -LiteralPath $expected -Raw -Encoding UTF8 | ConvertFrom-Json).PSObject.Properties.Name)
if (Compare-Object $names @($files | ForEach-Object BaseName)) {
    throw 'The .mdx files and the keys of reports/expected.json differ.'
}
[void][IO.Directory]::CreateDirectory($output)
$utf8 = New-Object Text.UTF8Encoding($false)
foreach ($file in $files) {
    $statement = [Security.SecurityElement]::Escape([IO.File]::ReadAllText($file.FullName, $utf8))
    $request = @"
<Execute xmlns="urn:schemas-microsoft-com:xml-analysis">
  <Command><Statement>$statement</Statement></Command>
  <Properties><PropertyList>
    <Catalog>P64SalesCube</Catalog><Format>Multidimensional</Format>
    <AxisFormat>TupleFormat</AxisFormat><Content>Data</Content>
  </PropertyList></Properties>
</Execute>
"@
    # A full Execute request is sent as it is (the Invoke-ASCmd/ascmd rule: text that is not an
    # XMLA command, Discover or Execute is wrapped in <Statement>). The answer is the XMLA
    # response text with the mddataset cellset; an XMLA error stays inside it and is not thrown.
    $answer = Invoke-ASCmd -Server $Server -Database P64SalesCube -Query $request -ErrorAction Stop
    [IO.File]::WriteAllText((Join-Path $output ($file.BaseName + '.xml')), [string]$answer, $utf8)
}
Write-Output "answers: $output"
$oldPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $root 'src'
    # Query by query first, so a failure still shows every answer; then the strict comparison.
    python -m sales_cube.mondrian report --engine SSAS $expected $output
    $reportCode = $LASTEXITCODE
    python -m sales_cube.cellset $expected $output --queries $queries
    if ($LASTEXITCODE -ne 0 -or $reportCode -ne 0) { throw 'MDX result comparison failed.' }
}
finally { $env:PYTHONPATH = $oldPath }
