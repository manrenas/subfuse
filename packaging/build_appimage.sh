#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
BUILD_ROOT="$ROOT/build_appimage"
APPDIR="$BUILD_ROOT/AppDir"
DIST="$ROOT/dist"
ARCH="$(uname -m)"

if [[ "$ARCH" != "x86_64" ]]; then
    printf 'The AppImage target is Linux x86_64; detected %s.\n' "$ARCH" >&2
    exit 1
fi
if ! command -v appimagetool >/dev/null 2>&1; then
    printf '%s\n' 'appimagetool is required to build the AppImage.' >&2
    exit 1
fi

"$PYTHON" -m PyInstaller \
    --noconfirm \
    --clean \
    --windowed \
    --name SubFuse \
    --distpath "$BUILD_ROOT/dist" \
    --workpath "$BUILD_ROOT/work" \
    --specpath "$BUILD_ROOT" \
    --add-data "$ROOT/legenda_app/assets/subfuse-icone.png:assets" \
    "$ROOT/embutir_legendas.py"

rm -rf "$APPDIR"
mkdir -p \
    "$APPDIR/usr/lib/subfuse" \
    "$APPDIR/usr/share/icons/hicolor/512x512/apps" \
    "$DIST"
cp -a "$BUILD_ROOT/dist/SubFuse/." "$APPDIR/usr/lib/subfuse/"
cp "$ROOT/packaging/AppRun" "$APPDIR/AppRun"
cp "$ROOT/packaging/SubFuse.desktop" "$APPDIR/SubFuse.desktop"
cp "$ROOT/legenda_app/assets/subfuse-icone.png" "$APPDIR/subfuse.png"
mkdir -p "$APPDIR/usr/share/doc/subfuse"
cp "$ROOT/legenda_app/assets/ICON-NOTICE.txt" \
    "$APPDIR/usr/share/doc/subfuse/ICON-NOTICE.txt"
cp "$ROOT/legenda_app/assets/subfuse-icone.png" \
    "$APPDIR/usr/share/icons/hicolor/512x512/apps/subfuse.png"
ln -s subfuse.png "$APPDIR/.DirIcon"
chmod +x "$APPDIR/AppRun"

VERSION="$("$PYTHON" -c 'from legenda_app import __version__; print(__version__)')"
APPIMAGE="$DIST/SubFuse-${VERSION}-linux-x86_64.AppImage"
APPIMAGE_ARGS=()
if [[ -n "${APPIMAGE_RUNTIME_FILE:-}" ]]; then
    if [[ ! -f "$APPIMAGE_RUNTIME_FILE" ]]; then
        printf 'AppImage runtime not found: %s\n' "$APPIMAGE_RUNTIME_FILE" >&2
        exit 1
    fi
    APPIMAGE_ARGS+=(--runtime-file "$APPIMAGE_RUNTIME_FILE")
fi

rm -f "$APPIMAGE"
ARCH="$ARCH" appimagetool "${APPIMAGE_ARGS[@]}" "$APPDIR" "$APPIMAGE"
APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGE" --version
printf 'Created %s\n' "$APPIMAGE"
