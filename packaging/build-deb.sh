#!/usr/bin/env bash
#
# Build one Debian package out of every plugin in this repo. The package
# installs each plugin under
#
#   /usr/share/albert/python/plugins/<name>
#
# which is the system-wide directory the Albert python plugin loader scans. The
# plugins are plain python packages, so the payload is a copy of plugins/<name>
# with the development-only bits (tests, demo media, byte-code caches) pruned.
#
# Usage:
#   packaging/build-deb.sh            # writes dist/albert-plugins_<v>_all.deb
#   VERSION=1.2.3 packaging/build-deb.sh
#   OUT_DIR=/tmp/out packaging/build-deb.sh
#
# The path of the built .deb is the only thing printed on success.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$here/.." && pwd)"

plugins_dir="$repo_root/plugins"
out_dir="${OUT_DIR:-$repo_root/dist}"

package="albert-plugins"
arch="all"
install_root="/usr/share/albert/python/plugins"
maintainer="Nikos Koukis <nickkouk@gmail.com>"
homepage="https://github.com/bergercookie/awesome-albert-plugins"

# ------------------------------------------------------------------ version
# Debian requires the upstream version to start with a digit, which a bare
# commit id does not, hence the 0.0.0+ prefix. A tag is used verbatim.
if [ -n "${VERSION:-}" ]; then
    version="$VERSION"
elif tag="$(git -C "$repo_root" describe --tags --exact-match 2>/dev/null)"; then
    version="${tag#v}"
else
    version="0.0.0+g$(git -C "$repo_root" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    if [ -n "$(git -C "$repo_root" status --porcelain 2>/dev/null)" ]; then
        version="$version.dirty"
    fi
fi

command -v dpkg-deb >/dev/null 2>&1 || {
    echo "build-deb.sh: dpkg-deb not found; install dpkg" >&2
    exit 1
}

# ------------------------------------------------------------------ payload
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

root="$work/${package}_${version}_${arch}"
tree="$root$install_root"
mkdir -p "$root/DEBIAN" "$tree"

count=0
for src in "$plugins_dir"/*/; do
    [ -f "$src/__init__.py" ] || continue
    name="$(basename "$src")"
    cp -a "$src" "$tree/$name"
    count=$((count + 1))
done

if [ "$count" -eq 0 ]; then
    echo "build-deb.sh: no plugins found under $plugins_dir" >&2
    exit 1
fi

# Runtime tree only: no caches, no test suites, no demo media.
find "$tree" -type d -name __pycache__ -prune -exec rm -rf {} \;
find "$tree" -type d -name .pytest_cache -prune -exec rm -rf {} \;
find "$tree" -type d -name test -prune -exec rm -rf {} \;
find "$tree" -type d -name misc -prune -exec rm -rf {} \;
find "$tree" -type f -name '*.pyc' -delete

installed_size="$(du -sk "$root" | cut -f1)"

# ------------------------------------------------------------------ control
cat > "$root/DEBIAN/control" <<EOF
Package: $package
Version: $version
Architecture: $arch
Maintainer: $maintainer
Installed-Size: $installed_size
Section: utils
Priority: optional
Homepage: $homepage
Description: Albert launcher python plugins
 A collection of $count python plugins for the Albert launcher, installed as a
 system-wide plugin directory for albert-plugin-python.
EOF

# ------------------------------------------------------------------ build
mkdir -p "$out_dir"
deb="$out_dir/${package}_${version}_${arch}.deb"
# --root-owner-group forces root:root ownership without needing fakeroot.
dpkg-deb --root-owner-group --build "$root" "$deb" >/dev/null
echo "$deb"
