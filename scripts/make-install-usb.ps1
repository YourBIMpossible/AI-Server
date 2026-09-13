<#
.SYNOPSIS
  Write an Ubuntu Server ISO to a USB stick as a bootable installer, and verify the write.

.DESCRIPTION
  Step 1 of relocate.md needs an install USB and the repo had no way to make one. This is
  that step, scripted, so a reinstall is repeatable rather than a Rufus session nobody
  wrote down.

  Ubuntu's live-server ISOs are isohybrid images: the raw bytes are simultaneously a valid
  ISO9660 filesystem and a valid GPT disk with an EFI System Partition. So the correct
  operation is a byte-for-byte copy to the whole physical device -- not a file copy, and
  not a partition-level write. Anything that "adds" a partition afterwards (or a previous
  half-finished write) leaves the stray-partition mess this script exists to clear.

  DESTRUCTIVE. Every byte on the target device is overwritten.

.PARAMETER IsoPath
  Path to the .iso. Must exist.

.PARAMETER DiskNumber
  Physical disk number from Get-Disk. Required and never guessed -- disk numbers move
  between boots, so the script re-validates the device it was handed (see the guards below)
  and aborts rather than trusting the number.

.PARAMETER ExpectedSha256
  Optional. If given, the ISO is hashed before writing and must match. Get it from
  https://releases.ubuntu.com/<release>/SHA256SUMS

.PARAMETER MaxSizeGB
  Refuse to write to a device larger than this. Defaults to 256, which is comfortably
  above any install stick and comfortably below any drive worth crying over.

.PARAMETER SkipVerify
  Skip the post-write readback. Don't: the readback is the only thing that distinguishes
  "wrote successfully" from "wrote to a dying stick".

.PARAMETER VerifyOnly
  Read the device back and compare it to the ISO, without writing anything. Non-destructive.
  Use it to re-check a stick you already wrote, or one that has been carried around.

.PARAMETER Force
  Skip the interactive confirmation. The caller is asserting they have already confirmed
  the target.

.EXAMPLE
  # From an ELEVATED PowerShell:
  .\make-install-usb.ps1 -IsoPath C:\Users\me\Downloads\ubuntu-26.04.1-live-server-amd64.iso -DiskNumber 3

.NOTES
  Requires Administrator. Raw device access is not available to a normal user.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$IsoPath,
    [Parameter(Mandatory = $true)][int]$DiskNumber,
    [string]$ExpectedSha256,
    [int]$MaxSizeGB = 256,
    [switch]$SkipVerify,
    [switch]$VerifyOnly,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-Step { param([string]$Text) Write-Host "`n==> $Text" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Text) Write-Host "    OK  $Text" -ForegroundColor Green }
function Fail       { param([string]$Text) Write-Host "`nABORT: $Text" -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------- preconditions

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Fail "Administrator required -- raw writes to \\.\PHYSICALDRIVE are not permitted otherwise. Re-run from an elevated PowerShell."
}

if (-not (Test-Path -LiteralPath $IsoPath)) { Fail "ISO not found: $IsoPath" }
$iso = Get-Item -LiteralPath $IsoPath
if ($iso.Length -lt 100MB) { Fail "$IsoPath is only $([math]::Round($iso.Length/1MB,1)) MB -- that is not an install ISO (truncated download?)." }

Write-Step "Source ISO"
Write-Host "    $($iso.FullName)"
Write-Host "    $([math]::Round($iso.Length/1GB,3)) GB"

if ($ExpectedSha256) {
    Write-Step "Verifying ISO checksum before touching the device"
    $actual = (Get-FileHash -LiteralPath $iso.FullName -Algorithm SHA256).Hash
    if ($actual -ne $ExpectedSha256.ToUpperInvariant().Trim()) {
        Fail "ISO SHA256 mismatch.`n      expected $($ExpectedSha256.ToUpperInvariant())`n      actual   $actual`n      Do not write a corrupt image; re-download it."
    }
    Write-Ok "SHA256 $actual"
}

# ---------------------------------------------------------------- target guards
# Each guard below has cost someone a drive at some point. None of them are optional.

$disk = Get-Disk -Number $DiskNumber -ErrorAction SilentlyContinue
if (-not $disk) { Fail "No disk $DiskNumber. Run Get-Disk and pass the right number." }

if ($disk.IsBoot)                { Fail "Disk $DiskNumber is the BOOT disk." }
if ($disk.IsSystem)              { Fail "Disk $DiskNumber is the SYSTEM disk." }
if ($disk.BusType -ne 'USB')     { Fail "Disk $DiskNumber is BusType '$($disk.BusType)', not USB. This script only writes removable USB media." }
if ($disk.Size -gt ($MaxSizeGB * 1GB)) {
    Fail "Disk $DiskNumber is $([math]::Round($disk.Size/1GB,1)) GB, over the $MaxSizeGB GB safety cap. If this really is your install stick, pass -MaxSizeGB."
}
if ($disk.Size -lt $iso.Length) {
    Fail "Disk $DiskNumber holds $([math]::Round($disk.Size/1GB,2)) GB but the ISO is $([math]::Round($iso.Length/1GB,2)) GB."
}

if ($VerifyOnly) {
    Write-Step "Target device -- VerifyOnly, nothing will be written"
} else {
    Write-Step "Target device -- EVERYTHING ON IT WILL BE DESTROYED"
}
Write-Host "    Disk $DiskNumber  $($disk.FriendlyName)"
Write-Host "    $([math]::Round($disk.Size/1GB,2)) GB  $($disk.BusType)  $($disk.PartitionStyle)"
$parts = @(Get-Partition -DiskNumber $DiskNumber -ErrorAction SilentlyContinue)
if ($parts.Count) {
    Write-Host $(if ($VerifyOnly) { "    Current partitions:" } else { "    Existing partitions to be erased:" })
    foreach ($p in $parts) {
        $letter = if ($p.DriveLetter) { "$($p.DriveLetter):" } else { '(no letter)' }
        Write-Host ("      #{0}  {1,-12} {2,8:N2} GB  {3}" -f $p.PartitionNumber, $letter, ($p.Size / 1GB), $p.Type)
    }
}

if (-not $Force -and -not $VerifyOnly) {
    $answer = Read-Host "`nType the disk number ($DiskNumber) to confirm destruction, anything else to abort"
    if ($answer -ne "$DiskNumber") { Fail "Not confirmed." }
}

# ---------------------------------------------------------------- clear + offline
# Windows must not be holding the volumes when we open the raw device, or the write
# succeeds into a cached void and the stick boots to nothing.

$tookOffline = $false
if (-not $VerifyOnly) {
    Write-Step "Clearing the existing partition table"
    Clear-Disk -Number $DiskNumber -RemoveData -RemoveOEM -Confirm:$false
    Write-Ok "partition table cleared"

    # Clear-Disk already dismounted every volume, which is the part that matters. Taking the
    # disk offline on top of that is belt-and-braces for FIXED disks -- and removable media
    # rejects it outright ("Removable media cannot be set to offline"), so both of these are
    # best-effort and a failure here is not a failure of the write.
    Write-Step "Making sure Windows is not holding the device"
    try {
        Set-Disk -Number $DiskNumber -IsReadOnly $false -ErrorAction Stop
    } catch {
        Write-Host "    (read-only flag not settable on this device; continuing)" -ForegroundColor DarkGray
    }
    try {
        Set-Disk -Number $DiskNumber -IsOffline $true -ErrorAction Stop
        $tookOffline = $true
        Write-Ok "offline"
    } catch {
        Write-Host "    (removable media cannot go offline; Clear-Disk already released the volumes)" -ForegroundColor DarkGray
    }
}

# ---------------------------------------------------------------- raw write

$devicePath = "\\.\PHYSICALDRIVE$DiskNumber"
$bufferSize = 8MB
$buffer = New-Object byte[] $bufferSize
$written = 0L
$sw = [Diagnostics.Stopwatch]::StartNew()

if (-not $VerifyOnly) {
Write-Step "Writing $([math]::Round($iso.Length/1GB,2)) GB to $devicePath"
$src = $null; $dst = $null
try {
    $src = [IO.File]::Open($iso.FullName, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $dst = New-Object IO.FileStream($devicePath, [IO.FileMode]::Open, [IO.FileAccess]::Write, [IO.FileShare]::None)

    while ($true) {
        $read = $src.Read($buffer, 0, $bufferSize)
        if ($read -le 0) { break }
        # Physical-device writes must be whole sectors. The final short read is padded to
        # the 8MB buffer, which is sector-aligned; the trailing zeroes land past the image
        # and are harmless.
        $chunk = if ($read -eq $bufferSize) { $read } else { [int][math]::Ceiling($read / 4096) * 4096 }
        if ($chunk -gt $bufferSize) { $chunk = $bufferSize }
        $dst.Write($buffer, 0, $chunk)
        $written += $read
        $pct = [math]::Round(($written / $iso.Length) * 100, 1)
        $mbs = if ($sw.Elapsed.TotalSeconds -gt 0) { [math]::Round(($written / 1MB) / $sw.Elapsed.TotalSeconds, 1) } else { 0 }
        Write-Progress -Activity "Writing to disk $DiskNumber" -Status "$pct%  ($([math]::Round($written/1GB,2)) GB, $mbs MB/s)" -PercentComplete ([math]::Min($pct, 100))
    }
    $dst.Flush($true)
}
finally {
    if ($dst) { $dst.Dispose() }
    if ($src) { $src.Dispose() }
    Write-Progress -Activity "Writing to disk $DiskNumber" -Completed
}
$sw.Stop()
Write-Ok "$([math]::Round($written/1GB,3)) GB written in $([math]::Round($sw.Elapsed.TotalSeconds,1))s"
}

# ---------------------------------------------------------------- verify

if (-not $SkipVerify) {
    Write-Step "Reading the device back and comparing hashes"
    $sha = [Security.Cryptography.SHA256]::Create()
    $rs = $null
    try {
        $rs = New-Object IO.FileStream($devicePath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None)
        $remaining = $iso.Length
        while ($remaining -gt 0) {
            # [int64] on both arguments, every time: $remaining exceeds Int32 for any ISO
            # over 2GB, and [math]::Min would otherwise resolve to the (int,int) overload
            # off the Int32 $bufferSize and throw mid-verify.
            $want = [int][math]::Min([int64]$bufferSize, [int64]$remaining)
            $got = $rs.Read($buffer, 0, [int][math]::Ceiling($want / 4096) * 4096)
            if ($got -le 0) { break }
            $use = [int][math]::Min([int64]$got, [int64]$remaining)
            $sha.TransformBlock($buffer, 0, $use, $null, 0) | Out-Null
            $remaining -= $use
            $done = $iso.Length - $remaining
            Write-Progress -Activity "Verifying disk $DiskNumber" -Status "$([math]::Round(($done/$iso.Length)*100,1))%" -PercentComplete ([math]::Min(($done / $iso.Length) * 100, 100))
        }
        $sha.TransformFinalBlock(@(), 0, 0) | Out-Null
    }
    finally {
        if ($rs) { $rs.Dispose() }
        Write-Progress -Activity "Verifying disk $DiskNumber" -Completed
    }

    $onDisk = ($sha.Hash | ForEach-Object { $_.ToString('x2') }) -join ''
    $onFile = (Get-FileHash -LiteralPath $iso.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($onDisk -ne $onFile) {
        Fail "READBACK MISMATCH -- the stick does not contain the image.`n      iso    $onFile`n      device $onDisk`n      Try a different USB port or a different stick; this one is not trustworthy."
    }
    Write-Ok "device matches ISO byte-for-byte ($onDisk)"
}

# ---------------------------------------------------------------- finish

if ($tookOffline) {
    Write-Step "Bringing the disk back online"
    try { Set-Disk -Number $DiskNumber -IsOffline $false } catch { Write-Host "    (left offline; unplug and replug is fine)" -ForegroundColor DarkGray }
}

Write-Host "`nDONE. Disk $DiskNumber is a bootable Ubuntu installer." -ForegroundColor Green
Write-Host @"

Windows will likely offer to format a partition on this stick. Say NO -- that prompt is
Windows failing to read the Linux partitions, not a problem with the stick.

Next, on the box, BEFORE installing (see relocate.md step 0):
  - BIOS: microcode 0x12B or newer, and the Intel Default power profile.
    An always-on 14900K on an unlimited profile is the exact duty cycle that
    surfaces the 13th/14th-gen voltage degradation issue.
  - Boot the stick in UEFI mode, not legacy/CSM.
"@ -ForegroundColor Gray
