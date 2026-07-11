#!/bin/zsh
# Report 032 WP-B/WP-D: 13 recipes x 1 lighting, HDRI pack, production config,
# rendered twice with IDENTICAL seeds: specular OFF vs ON (extractor A/B).
set -u
cd /Users/dominiquepiche-meunier/Documents/vitraux/.claude/worktrees/agent-a90728859ff9fb3d5/research/delighting
BL=~/Applications/Blender-5.0.1.app/Contents/MacOS/Blender
HD=/tmp/hdri_pack_032
recipes=(cathedral-green cathedral-amber dark-opaque streaky-mix wispy-white dark-deep dark-ruby dark-slate cathedral-blue cathedral-red saturated-opalescent streaky-fine-texture dark-textured)
rm -rf /tmp/b032_off /tmp/b032_on; mkdir -p /tmp/b032_off /tmp/b032_on
i=0
for r in $recipes; do
  seed=$((500+i)); i=$((i+1))
  PYTHONPATH=~/.local/lib/python3.11/site-packages $BL -b --python-use-system-env -P generate_synthetic.py -- \
    --out /tmp/b032_off --seed $seed --count 1 --light-variations 1 --recipe $r --hdri-dir $HD >/dev/null 2>&1
  echo "OFF $r exit=$?"
done
i=0
for r in $recipes; do
  seed=$((500+i)); i=$((i+1))
  PYTHONPATH=~/.local/lib/python3.11/site-packages $BL -b --python-use-system-env -P generate_synthetic.py -- \
    --out /tmp/b032_on --seed $seed --count 1 --light-variations 1 --recipe $r --hdri-dir $HD --specular >/dev/null 2>&1
  echo "ON $r exit=$?"
done
echo BATCH032_DONE
