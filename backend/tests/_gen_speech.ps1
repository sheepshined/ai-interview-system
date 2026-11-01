# 用 Windows 自带 SAPI TTS 离线合成中文测试语音 (ASR 测试用, 无需联网)
param([string]$OutFile, [string]$Text)
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$zh = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'zh*' } | Select-Object -First 1
if ($zh) { $s.SelectVoice($zh.VoiceInfo.Name) }
$s.SetOutputToWaveFile($OutFile)
$s.Speak($Text)
$s.Dispose()
Write-Output "OK voice=$($zh.VoiceInfo.Name) file=$OutFile"
