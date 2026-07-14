#!/usr/bin/env bash
set -euo pipefail
root="${ZHIJIA_DATA_ROOT:-/data5/lzx_data/Zhijia-Guardian}/reference/openpilot"
mkdir -p "$(dirname "$root")"
if [ -d "$root/.git" ]; then
  git -C "$root" fetch --depth 1 origin
  git -C "$root" reset --hard origin/master
else
  git clone --depth 1 --filter=blob:none https://github.com/commaai/openpilot.git "$root"
fi
git -C "$root" submodule update --init --depth 1 opendbc_repo
echo "$root"
