$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$secretPath = Join-Path $projectRoot '.env'
$fileAcl = Get-Acl -LiteralPath $secretPath
# Preserve the owner, application runtime accounts and Windows administrators.
# Freeze existing restricted permissions so project-folder sharing cannot expand them.
$fileAcl.SetAccessRuleProtection($true, $true)
foreach ($rule in @($fileAcl.Access)) {
    $identity = $rule.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
    if ($identity -in @('S-1-1-0', 'S-1-5-11', 'S-1-5-32-545')) {
        $fileAcl.RemoveAccessRuleSpecific($rule)
    }
}
Set-Acl -LiteralPath $secretPath -AclObject $fileAcl
Write-Host 'Backend credential file permissions protected. Secret withheld.'
