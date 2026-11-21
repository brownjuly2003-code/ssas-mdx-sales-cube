[CmdletBinding()]
param(
    # Optional directory containing the net472 AMO assemblies from Microsoft.AnalysisServices.
    [string]$AmoDirectory
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Amo.ps1')
$loaded = Import-Amo -AmoDirectory $AmoDirectory
Write-Output ("AMO {0} from {1}" -f [Microsoft.AnalysisServices.Database].Assembly.GetName().Version, $loaded)
$path = Join-Path (Split-Path -Parent $PSScriptRoot) 'cube/create.xmla'
[xml]$xml = Get-Content -LiteralPath $path -Raw -Encoding UTF8
$reader = New-Object Xml.XmlNodeReader $xml.Create.ObjectDefinition.Database
$db = New-Object Microsoft.AnalysisServices.Database
try {
    [void][Microsoft.AnalysisServices.Utils]::Deserialize($reader, $db)
    $issues = New-Object Microsoft.AnalysisServices.ValidationResultCollection
    if (-not $db.Validate($issues, [Microsoft.AnalysisServices.ValidationOptions]::AddDetails,
                          [Microsoft.AnalysisServices.ServerEdition]::Developer)) {
        throw (($issues | ForEach-Object { "$($_.SourcePath) $($_.Description)" }) -join [Environment]::NewLine)
    }
    $cube = $db.Cubes.FindByName('Sales')
    Write-Output ("{0}: {1} dimensions, {2} measure group, {3} measures" -f $db.Name,
                  $db.Dimensions.Count, $cube.MeasureGroups.Count, $cube.MeasureGroups[0].Measures.Count)
} finally {
    $reader.Close()
    $db.Dispose()
}
