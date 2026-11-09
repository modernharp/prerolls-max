#!/usr/bin/env bash
# Builds the three Prerolls Max Intros plugins and packages them into ./out:
#
#   PrerollsMax.Jellyfin-10.11-<version>.zip   Jellyfin 10.11.x (.NET 9)
#   PrerollsMax.Jellyfin-12-<version>.zip      Jellyfin 12.x    (.NET 10)
#   PrerollsMax.Emby-<version>.zip             Emby 4.9 and later (.NET 8)
#   PrerollsMax.Emby.dll                       the same Emby plugin, unzipped
#
# Needs only the .NET 10 SDK (it builds the .NET 8 and 9 targets too) and
# internet access to nuget.org. No media server DLLs are needed or committed.
# The version comes from Directory.Build.props.
#
#   ./build.sh            build everything
#   DOTNET=/path/dotnet ./build.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOTNET="${DOTNET:-dotnet}"
OUT="$HERE/out"
export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1

VERSION="$("$DOTNET" msbuild "$HERE/PrerollsMax.Jellyfin/PrerollsMax.Jellyfin.csproj" -getProperty:PrerollsMaxPluginVersion -p:TargetFramework=net9.0 | tr -d '[:space:]')"
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Couldn't read the plugin version from Directory.Build.props (got '$VERSION')." >&2
  exit 1
fi
echo "Prerolls Max Intros $VERSION"

rm -rf "$OUT"
mkdir -p "$OUT"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

"$DOTNET" build "$HERE/PrerollsMax.Jellyfin/PrerollsMax.Jellyfin.csproj" -c Release --nologo -v quiet
"$DOTNET" build "$HERE/PrerollsMax.Emby/PrerollsMax.Emby.csproj" -c Release --nologo -v quiet

# Zips with fixed timestamps and order, so the same sources give the same bytes.
make_zip() {
  local zip="$1"; shift
  if ! command -v python3 >/dev/null 2>&1; then
    # No Python (the .NET SDK image): fixed timestamps with zip -X instead.
    touch -d "2020-01-01 00:00:00" "$@"
    zip -q -X -j "$zip" $(printf '%s\n' "$@" | sort)
    return
  fi
  python3 - "$zip" "$@" <<'PY'
import sys, zipfile, os
target, files = sys.argv[1], sys.argv[2:]
with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
    for path in sorted(files, key=os.path.basename):
        info = zipfile.ZipInfo(os.path.basename(path), date_time=(2020, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        with open(path, "rb") as fh:
            z.writestr(info, fh.read())
PY
}

jellyfin_package() {
  local series="$1" tfm="$2" abi="$3"
  local dir="$STAGE/jellyfin-$series"
  mkdir -p "$dir"
  cp "$HERE/PrerollsMax.Jellyfin/bin/Release/$tfm/PrerollsMax.Jellyfin.dll" "$dir/"
  cp "$HERE/PrerollsMax.Jellyfin/thumb.png" "$dir/"
  cat > "$dir/meta.json" <<JSON
{
  "guid": "c0a6ea94-7795-4b61-b964-4ddfb93ec8b0",
  "name": "Prerolls Max Intros",
  "description": "Plays intro videos chosen by Prerolls Max before movies and episodes.",
  "overview": "Intro videos from Prerolls Max for Jellyfin $series.",
  "owner": "Prerolls Max",
  "category": "General",
  "version": "$VERSION",
  "targetAbi": "$abi",
  "framework": "$tfm",
  "imagePath": "thumb.png",
  "status": "Active",
  "autoUpdate": false
}
JSON
  make_zip "$OUT/PrerollsMax.Jellyfin-$series-$VERSION.zip" "$dir/PrerollsMax.Jellyfin.dll" "$dir/meta.json" "$dir/thumb.png"
}

jellyfin_package "10.11" "net9.0" "10.11.0.0"
jellyfin_package "12" "net10.0" "12.0.0.0"

cp "$HERE/PrerollsMax.Emby/bin/Release/net8.0/PrerollsMax.Emby.dll" "$OUT/PrerollsMax.Emby.dll"
make_zip "$OUT/PrerollsMax.Emby-$VERSION.zip" "$OUT/PrerollsMax.Emby.dll"

echo "Packages:"
ls -l "$OUT"
