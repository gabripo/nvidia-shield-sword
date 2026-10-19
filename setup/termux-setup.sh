#!/data/data/com.termux/files/usr/bin/bash
# Runs inside Termux on the Shield (piped over SSH by setup/install.sh).
# Installs proot-distro and creates the Debian container "debian".
set -euo pipefail

echo "==> Termux: installing proot-distro, curl"
yes | pkg install -y -o Dpkg::Options::=--force-confnew proot-distro curl >/dev/null

ver=$(dpkg-query -W -f='${Version}' proot-distro)
echo "    proot-distro $ver"
if [ "${ver%%.*}" -lt 5 ]; then
  echo "!! proot-distro $ver is older than 5.x. Your Termux mirror is probably stale." >&2
  echo "!! Pin the official mirror and upgrade, then re-run:" >&2
  echo "!!   ln -sf \$PREFIX/etc/termux/mirrors/default \$PREFIX/etc/termux/chosen_mirrors" >&2
  echo "!!   pkg --check-mirror update && pkg upgrade" >&2
  exit 1
fi

if proot-distro list 2>/dev/null | grep -qE '^\s*\*?\s*debian\b'; then
  echo "==> Debian container already installed"
else
  echo "==> Installing Debian trixie as container 'debian' (downloads ~50 MB)"
  proot-distro install debian:trixie --name debian
fi

mkdir -p "$HOME/.termux/boot"
echo "==> Termux setup done"
