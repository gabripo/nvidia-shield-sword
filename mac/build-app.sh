#!/bin/zsh
# Build mac/build/Shield.app from Shield.applescript and icon/shield-icon.svg.
# Uses macOS tools (osacompile, sips, iconutil, codesign) plus `swift` from the
# Xcode Command Line Tools for a transparent icon.
set -euo pipefail
HERE="${0:A:h}"
OUT="$HERE/build"
rm -rf "$OUT" && mkdir -p "$OUT"

echo "==> Compiling Shield.app"
osacompile -o "$OUT/Shield.app" "$HERE/Shield.applescript"

echo "==> Rendering icon"
# AppKit renders the SVG (gradients, blur) onto a transparent canvas. Needs `swift`
# (Xcode Command Line Tools). Quick Look is the fallback, but its thumbnails have a
# white background instead of transparency.
if command -v swift >/dev/null && swift "$HERE/icon/render-icon.swift" "$HERE/icon/shield-icon.svg" "$OUT/icon-1024.png" 1024; then
  :
else
  echo "   swift unavailable - using Quick Look (icon corners will be white; xcode-select --install fixes this)"
  qlmanage -t -s 1024 -o "$OUT" "$HERE/icon/shield-icon.svg" >/dev/null 2>&1
  mv "$OUT/shield-icon.svg.png" "$OUT/icon-1024.png"
fi
mkdir "$OUT/Shield.iconset"
for s in 16 32 128 256 512; do
  sips -z $s $s "$OUT/icon-1024.png" --out "$OUT/Shield.iconset/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) "$OUT/icon-1024.png" --out "$OUT/Shield.iconset/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$OUT/Shield.iconset" -o "$OUT/Shield.app/Contents/Resources/applet.icns"
rm -rf "$OUT/Shield.iconset"

echo "==> Signing (ad hoc)"
codesign --force --sign - "$OUT/Shield.app" 2>/dev/null
codesign --verify "$OUT/Shield.app"
echo "Built $OUT/Shield.app"
