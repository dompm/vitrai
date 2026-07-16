#!/bin/bash
# Report 048: render the 12 oracle-045 recipe families through the real generator
# (validate/uniform backlight -> no HDRI needed) so gt_sigma_s / gt_a_glow land on disk
# via the actual export path. Sequential (one Blender at a time, machine rule). Slow.
set -u
cd "$(dirname "$0")/../.."   # research/delighting
BL="$HOME/Applications/Blender-5.0.1.app/Contents/MacOS/Blender"
export BL_SCIPY_PATH=/tmp/bl_scipy_pkg
OUT=results/048/gen_data
rm -rf "$OUT"; mkdir -p "$OUT"
PAIRS=(
  cathedral-green:6001 cathedral-amber:6002 streaky-mix:6001 streaky-fine-texture:6002
  wispy-white:6001 saturated-opalescent:6001 ring-mottle:6001 dark-ruby:6001
  dark-textured:6002 baroque-rolling-wave:6001 confetti-shard:6002 fracture-streamer:6003
)
for pair in "${PAIRS[@]}"; do
  recipe="${pair%:*}"; seed="${pair#*:}"
  echo "=== RENDER $recipe seed=$seed ==="
  "$BL" -b -P results/048/gen048_blender.py -- \
      --out "$OUT" --recipe "$recipe" --seed "$seed" --count 1 \
      --light-variations 1 --validate --no-tex-dump \
      2>&1 | grep -viE "Deprecat|use_nodes" | grep -E "Generating|Saved|Fra:|Error|Traceback|Time:" | tail -4
done
echo "=== ALL DONE ==="
ls -d "$OUT"/*/ 2>/dev/null | wc -l
