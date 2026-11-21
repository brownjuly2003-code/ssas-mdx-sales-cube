[CmdletBinding()]
param(
    [string]$Server = 'localhost',
    [string]$AmoDirectory,
    # Windows service of the instance; MSSQLServerOLAPService is the default instance.
    [string]$ServiceName = 'MSSQLServerOLAPService'
)
# Prints version, edition and server mode of Analysis Services; fails unless the mode is Multidimensional.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Amo.ps1')
$loaded = Import-Amo -AmoDirectory $AmoDirectory
Write-Output ("AMO {0} from {1}" -f [Microsoft.AnalysisServices.Server].Assembly.GetName().Version, $loaded)
$instance = Connect-AnalysisServer -Server $Server -Attempts 12
try {
    Write-Output "Analysis Services product: $($instance.ProductName)"
    Write-Output "Analysis Services version: $($instance.Version)"
    Write-Output "Analysis Services edition: $($instance.Edition)"
    Write-Output "Analysis Services server mode (AMO ServerMode): $($instance.ServerMode)"
    $mode = [string]$instance.ServerMode
} finally {
    $instance.Disconnect()
}
# Second witness: DeploymentMode in msmdsrv.ini (0 = Multidimensional, 1 = PowerPivot, 2 = Tabular).
$service = Get-CimInstance Win32_Service -Filter "Name='$ServiceName'"
if ($service -and $service.PathName -match '-s\s+"([^"]+)"') {
    $ini = Join-Path $Matches[1] 'msmdsrv.ini'
    if (Test-Path -LiteralPath $ini) {
        [xml]$config = Get-Content -LiteralPath $ini -Raw
        Write-Output "msmdsrv.ini DeploymentMode: $($config.ConfigurationSettings.DeploymentMode) ($ini)"
    }
}
if ($mode -ne 'Multidimensional') {
    throw "Analysis Services runs in $mode mode; the cube needs Multidimensional."
}
