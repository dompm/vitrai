#!/usr/bin/env python3
"""Aggregate the 029 VLM realism-critique calls: print each verdict + truth label side
by side (to compute the calibration false-positive rate), and dump all OBSERVATIONS
lines grouped by call for manual theme-tagging in the report.
"""
import glob
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "results/vlm_realism_029/vlm_raw")

rows = []
for fp in sorted(glob.glob(os.path.join(RAW, "*.json"))):
    d = json.load(open(fp))
    stdout = d.get("stdout", "")
    m = re.search(r"VERDICT:\s*(.*)", stdout)
    verdict = m.group(1).strip() if m else "<NO VERDICT PARSED>"
    obs = re.findall(r"^-\s+(.*)$", stdout, re.MULTILINE)
    rows.append({
        "call_id": d["call_id"],
        "truth_label": d["truth_label"],
        "n_images": len(d["images"]),
        "images": [os.path.basename(p) for p in d["images"]],
        "elapsed_s": d.get("elapsed_s"),
        "returncode": d.get("returncode"),
        "verdict": verdict,
        "n_observations": len(obs),
        "observations": obs,
    })

print(f"{'call_id':32s} {'truth':22s} {'rc':3s} {'n_obs':5s} verdict")
for r in rows:
    print(f"{r['call_id']:32s} {r['truth_label']:22s} {r['returncode']:<3} {r['n_observations']:<5} {r['verdict'][:110]}")

print("\n--- FULL DUMP ---\n")
for r in rows:
    print(f"### {r['call_id']}  [{r['truth_label']}]  images={r['images']}")
    for o in r["observations"]:
        print(f"  - {o}")
    print(f"  VERDICT: {r['verdict']}")
    print()

with open(os.path.join(HERE, "results/vlm_realism_029/aggregate.json"), "w") as f:
    json.dump(rows, f, indent=2)
