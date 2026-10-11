#!/usr/bin/env bash
# Install the tested upstream binary on Fedora/Nobara or Kubuntu.
# Download as the current user; elevate only the final install if needed.
set -euo pipefail

if command -v rustic >/dev/null 2>&1; then
    installed=$(rustic --version 2>/dev/null || true)
    if python3 -c 'import re, sys; m = re.search(r"(\d+)\.(\d+)\.(\d+)", sys.argv[1]); sys.exit(0 if m and tuple(map(int, m.groups())) >= (0, 11, 4) else 1)' "$installed"; then
        printf 'Using existing %s\n' "$installed"
        exit 0
    fi
fi

case "$(uname -m)" in
    x86_64)
        target=x86_64-unknown-linux-gnu
        checksum=c20bc3682c6275de3cfbc9317101dca5c0800a2fb5c610d0f9ef2addfd27cf81
        ;;
    aarch64|arm64)
        target=aarch64-unknown-linux-gnu
        checksum=8d8121f9d72f5320e8a3dd870bce6cf56a4fb8cb4dadc4d29b4eeb228bd88406
        ;;
    *)
        printf 'Unsupported architecture. Install rustic >= 0.11.4 from https://rustic.cli.rs/docs/installation/\n' >&2
        exit 1
        ;;
esac

install_dir=${1:-/usr/local/bin}
work_dir=$(mktemp -d)
trap 'rm -rf -- "$work_dir"' EXIT
archive="$work_dir/rustic.tar.gz"
curl --fail --location --retry 3 --output "$archive" \
    "https://github.com/rustic-rs/rustic/releases/download/v0.11.4/rustic-v0.11.4-${target}.tar.gz"
if ! printf '%s  %s\n' "$checksum" "$archive" | sha256sum --check --status; then
    printf 'rustic download failed SHA-256 verification; nothing installed.\n' >&2
    exit 1
fi
# Extract only the binary, after verifying the complete archive.
tar --no-same-owner -xzf "$archive" -C "$work_dir" rustic
"$work_dir/rustic" --version >/dev/null
if [[ -d "$install_dir" && -w "$install_dir" ]]; then
    install -m 0755 "$work_dir/rustic" "$install_dir/rustic"
else
    sudo install -D -m 0755 "$work_dir/rustic" "$install_dir/rustic"
fi
"$install_dir/rustic" --version
