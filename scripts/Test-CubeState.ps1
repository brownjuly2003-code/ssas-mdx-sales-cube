[CmdletBinding()]
param(
    [string]$Server = 'localhost',
    [string]$AmoDirectory,
    # Rows of the dimension tables in the star, for example @{ Date = 731; Product = 6; Customer = 4 }.
    [Parameter(Mandatory = $true)][hashtable]$ExpectedMembers,
    # Folder for the raw XMLA answers of the checks.
    [Parameter(Mandatory = $true)][string]$OutDir
)
# After ProcessFull: the database, cube, dimensions and the partition are Processed, the partition
# is stored as MOLAP, and every key level holds as many members as its dimension table has rows.
$ErrorActionPreference = 'Stop'
Import-Module SqlServer -ErrorAction Stop
. (Join-Path $PSScriptRoot 'Amo.ps1')
[void](Import-Amo -AmoDirectory $AmoDirectory)
$target = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutDir)
[void][IO.Directory]::CreateDirectory($target)
$utf8 = New-Object Text.UTF8Encoding($false)
$failures = New-Object Collections.Generic.List[string]

function Test-Value([string]$What, $Actual, $Expected) {
    $ok = [string]$Actual -eq [string]$Expected
    Write-Output ('{0}: {1} (expected {2}) {3}' -f $What, $Actual, $Expected, $(if ($ok) { 'ok' } else { 'MISMATCH' }))
    if (-not $ok) { $failures.Add($What) }
}

function Send-Xmla([string]$Name, [string]$Request) {
    $answer = [string](Invoke-ASCmd -Server $Server -Query $Request -ErrorAction Stop)
    [IO.File]::WriteAllText((Join-Path $target "$Name.xml"), $answer, $utf8)
    [xml]$xml = $answer
    $errors = $xml.SelectNodes("//*[local-name()='Exception' or local-name()='Error']")
    if ($errors.Count -gt 0) {
        throw "$Name returned an XMLA error: $(($errors | ForEach-Object { $_.GetAttribute('Description') }) -join '; ')"
    }
    $xml
}

$instance = Connect-AnalysisServer -Server $Server
try {
    $db = $instance.Databases.FindByName('P64SalesCube')
    if (-not $db) { throw 'Database P64SalesCube is not on the server.' }
    Write-Output "Database P64SalesCube: State $($db.State), LastProcessed $($db.LastProcessed), EstimatedSize $($db.EstimatedSize)"
    Test-Value 'database state' $db.State 'Processed'
    foreach ($dimension in $db.Dimensions) {
        Write-Output "Dimension $($dimension.Name): State $($dimension.State), LastProcessed $($dimension.LastProcessed)"
        Test-Value "dimension $($dimension.Name) state" $dimension.State 'Processed'
    }
    $cube = $db.Cubes.FindByName('Sales')
    if (-not $cube) { throw 'Cube Sales is not in P64SalesCube.' }
    Write-Output "Cube Sales: State $($cube.State), LastProcessed $($cube.LastProcessed), StorageMode $($cube.StorageMode)"
    Test-Value 'cube state' $cube.State 'Processed'
    $partitionNames = @()
    foreach ($group in $cube.MeasureGroups) {
        Write-Output "Measure group $($group.Name): State $($group.State), StorageMode $($group.StorageMode)"
        foreach ($partition in $group.Partitions) {
            Write-Output ("Partition {0}: State {1}, StorageMode {2}, LastProcessed {3}, EstimatedSize {4} bytes" -f
                $partition.Name, $partition.State, $partition.StorageMode, $partition.LastProcessed, $partition.EstimatedSize)
            Test-Value "partition $($partition.Name) state" $partition.State 'Processed'
            Test-Value "partition $($partition.Name) storage mode" $partition.StorageMode 'Molap'
            $partitionNames += , @($group.Name, $partition.Name)
        }
    }
    if ($partitionNames.Count -ne 1) { $failures.Add("one partition expected, found $($partitionNames.Count)") }
} finally {
    $instance.Disconnect()
}

# Rows and size of the partition as the server reports them; informative, not a pass condition.
foreach ($pair in $partitionNames) {
    $discover = @"
<Discover xmlns="urn:schemas-microsoft-com:xml-analysis">
  <RequestType>DISCOVER_PARTITION_STAT</RequestType>
  <Restrictions><RestrictionList>
    <DATABASE_NAME>P64SalesCube</DATABASE_NAME><CUBE_NAME>Sales</CUBE_NAME>
    <MEASURE_GROUP_NAME>$($pair[0])</MEASURE_GROUP_NAME><PARTITION_NAME>$($pair[1])</PARTITION_NAME>
  </RestrictionList></Restrictions>
  <Properties><PropertyList><Content>Data</Content></PropertyList></Properties>
</Discover>
"@
    try {
        $stat = Send-Xmla "partition-stat-$($pair[1])" $discover
        foreach ($row in $stat.SelectNodes("//*[local-name()='row']")) {
            Write-Output ('DISCOVER_PARTITION_STAT: ' + (($row.ChildNodes | ForEach-Object { "$($_.LocalName)=$($_.InnerText)" }) -join ', '))
        }
    } catch {
        Write-Output "DISCOVER_PARTITION_STAT not available: $($_.Exception.Message)"
    }
}

# Members of the key level of each user hierarchy against the rows of the dimension table.
$levels = [ordered]@{
    Date     = '[Date].[Calendar].[Day]'
    Product  = '[Product].[Catalog].[Product]'
    Customer = '[Customer].[Geography].[Customer]'
}
foreach ($name in $levels.Keys) {
    $statement = "WITH MEMBER [Measures].[Member Count] AS Count($($levels[$name]).Members) " +
                 "SELECT {[Measures].[Member Count]} ON COLUMNS FROM [Sales]"
    $request = @"
<Execute xmlns="urn:schemas-microsoft-com:xml-analysis">
  <Command><Statement>$([Security.SecurityElement]::Escape($statement))</Statement></Command>
  <Properties><PropertyList>
    <Catalog>P64SalesCube</Catalog><Format>Multidimensional</Format>
    <AxisFormat>TupleFormat</AxisFormat><Content>Data</Content>
  </PropertyList></Properties>
</Execute>
"@
    $cells = (Send-Xmla "members-$name" $request).SelectNodes("//*[local-name()='Cell']/*[local-name()='Value']")
    $count = if ($cells.Count -eq 1) { [int][double]$cells[0].InnerText } else { "$($cells.Count) cells" }
    Test-Value "members of $($levels[$name])" $count $ExpectedMembers[$name]
}

if ($failures.Count -gt 0) { throw "Cube state checks failed: $($failures -join '; ')" }
Write-Output 'Cube state: database, dimensions, cube and partition Processed; partition MOLAP; key level members match the star'
