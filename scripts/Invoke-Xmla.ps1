[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Server,
    # An XMLA command file, for example cube/create.xmla or cube/process.xmla.
    [Parameter(Mandatory = $true)][string]$InputFile,
    # Where the answer of the server is saved as it was received.
    [Parameter(Mandatory = $true)][string]$OutFile
)
$ErrorActionPreference = 'Stop'
Import-Module SqlServer -ErrorAction Stop
$source = (Resolve-Path -LiteralPath $InputFile).Path
$target = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutFile)
[void][IO.Directory]::CreateDirectory((Split-Path -Parent $target))
$answer = [string](Invoke-ASCmd -Server $Server -InputFile $source -ErrorAction Stop)
[IO.File]::WriteAllText($target, $answer, (New-Object Text.UTF8Encoding($false)))
# Invoke-ASCmd returns the XMLA answer as text and does not fail when the answer reports
# an error, so the answer is read here: Exception and Error fail, Warning is printed.
try { [xml]$xml = $answer }
catch { throw "The answer to $InputFile is not XML: $answer" }
$problems = @()
foreach ($node in $xml.SelectNodes("//*[local-name()='Exception' or local-name()='Error' or local-name()='Warning']")) {
    $code = $node.GetAttribute('ErrorCode') + $node.GetAttribute('WarningCode')
    $line = '{0} {1} {2} {3}' -f $node.LocalName, $code, $node.GetAttribute('Description'), $node.GetAttribute('Source')
    Write-Output $line
    if ($node.LocalName -ne 'Warning') { $problems += $line }
}
if ($problems.Count -gt 0) {
    throw "$InputFile failed on $Server ($($problems.Count) error elements); the answer is saved in $OutFile"
}
Write-Output "$InputFile executed on ${Server}: no Exception or Error in the XMLA answer ($($answer.Length) characters, saved in $OutFile)"
