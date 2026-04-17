@{
    Severity = @('Error', 'Warning')
    ExcludeRules = @(
        # Interactive installer; colored TTY output via Write-Host is a deliberate UX choice.
        # Rule predates PS 5.0 redirection of Write-Host to the information stream (6>).
        'PSAvoidUsingWriteHost'
        # False positive: $Only/$Skip/$DryRun/$Force/$ClaudeSettings are script-level params
        # referenced from within functions via script scope. PSSA's scope analysis misses this.
        'PSReviewUnusedParameter'
    )
}
