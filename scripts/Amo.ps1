# Dot-source this file: . (Join-Path $PSScriptRoot 'Amo.ps1')
# Windows PowerShell 5.1 only: the root folder of the SqlServer module holds the .NET Framework AMO assemblies.

function Import-Amo {
    param(
        # A folder with the net472 assemblies Microsoft.AnalysisServices.Core.dll and Microsoft.AnalysisServices.dll.
        [string]$AmoDirectory
    )
    if (-not $AmoDirectory) {
        # The SqlServer manifest declares no RequiredAssemblies, so importing the module alone
        # does not make the AMO types available; load them from the module folder.
        Import-Module SqlServer -ErrorAction Stop
        $AmoDirectory = (Get-Module SqlServer | Select-Object -First 1).ModuleBase
    }
    foreach ($library in 'Microsoft.AnalysisServices.Core.dll', 'Microsoft.AnalysisServices.dll') {
        [void][Reflection.Assembly]::LoadFrom((Join-Path $AmoDirectory $library))
    }
    $AmoDirectory
}

function Connect-AnalysisServer {
    param(
        [Parameter(Mandatory = $true)][string]$Server,
        # A service that has just started may refuse connections for a few seconds.
        [int]$Attempts = 1
    )
    for ($attempt = 1; ; $attempt++) {
        $instance = New-Object Microsoft.AnalysisServices.Server
        try {
            $instance.Connect("Data Source=$Server")
            return , $instance
        } catch {
            if ($attempt -ge $Attempts) { throw }
            Write-Warning "Connection to $Server, attempt ${attempt}: $($_.Exception.Message)"
            Start-Sleep -Seconds 5
        }
    }
}
