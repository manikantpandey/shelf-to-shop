# Synthesise narration phrases with a Windows OneCore voice (Indian English by default).
# Used only to build synthetic test clips with exact timing ground truth.
# Usage: powershell -NoProfile -File spikes/tts_windows.ps1 -PhrasesJson phrases.json -OutDir out -Voice Heera
param(
    [Parameter(Mandatory = $true)][string]$PhrasesJson,
    [Parameter(Mandatory = $true)][string]$OutDir,
    [string]$Voice = "Heera"
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.Streams.DataReader, Windows.Storage.Streams, ContentType = WindowsRuntime] | Out-Null

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq "AsTask" -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq "IAsyncOperation``1"
    })[0]

function Wait-Op($op, [Type]$resultType) {
    $task = $asTaskGeneric.MakeGenericMethod($resultType).Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    return $task.Result
}

$synth = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
$match = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices | Where-Object { $_.DisplayName -like "*$Voice*" } | Select-Object -First 1
if ($null -eq $match) { throw "Voice '$Voice' is not installed" }
$synth.Voice = $match

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$phrases = Get-Content -Raw -Encoding UTF8 $PhrasesJson | ConvertFrom-Json
foreach ($p in $phrases) {
    $stream = Wait-Op ($synth.SynthesizeTextToStreamAsync($p.text)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
    $size = [uint32]$stream.Size
    $reader = New-Object Windows.Storage.Streams.DataReader($stream.GetInputStreamAt(0))
    Wait-Op ($reader.LoadAsync($size)) ([uint32]) | Out-Null
    $bytes = New-Object byte[] $size
    $reader.ReadBytes($bytes)
    [IO.File]::WriteAllBytes((Join-Path $OutDir ("{0}.wav" -f $p.id)), $bytes)
    "{0}: {1} bytes" -f $p.id, $size
}
