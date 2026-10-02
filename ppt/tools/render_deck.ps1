# Render a .pptx with the locally installed Microsoft PowerPoint (COM): PNG per slide, optional PDF.
#   powershell -File ppt/tools/render_deck.ps1 -Pptx ppt/Q-SHIELD_full_deck.pptx -OutDir ppt/preview/full [-Pdf ppt/Q-SHIELD_full_deck.pdf]
# Read-only: the source .pptx is opened read-only and never modified.
param(
    [Parameter(Mandatory = $true)][string]$Pptx,
    [Parameter(Mandatory = $true)][string]$OutDir,
    [string]$Pdf = ""
)
$ErrorActionPreference = "Stop"
$src = (Resolve-Path $Pptx).Path
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$out = (Resolve-Path $OutDir).Path
$app = New-Object -ComObject PowerPoint.Application
try {
    $pres = $app.Presentations.Open($src, -1, 0, 0)   # ReadOnly=true, Untitled=false, WithWindow=false
    $pres.Export($out, "PNG", 1600, 900)
    if ($Pdf -ne "") {
        $pdfPath = Join-Path (Resolve-Path (Split-Path $Pdf -Parent)).Path (Split-Path $Pdf -Leaf)
        $pres.SaveAs($pdfPath, 32)                     # ppSaveAsPDF
    }
    "slides: " + $pres.Slides.Count
    $pres.Close()
}
finally {
    # PowerPoint is a single shared instance: quit only if nothing else (for example a deck the user has open) remains.
    if ($app.Presentations.Count -eq 0) { $app.Quit() }
}
