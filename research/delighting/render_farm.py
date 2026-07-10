#!/usr/bin/env python3
"""render_farm.py -- seed-sharding launcher for generate_synthetic.py.

Report render-at-scale (see docs/RENDER_AT_SCALE.md): a single Blender/Cycles
process spends a large, MEASURED fraction of its wall time on single-threaded
CPU work (scene rebuild, numpy/scipy texture authoring, image encode/IO) and
on Cycles GT emission passes whose cost is dominated by fixed per-render-call
overhead, not sample count. During all of that the GPU sits idle; the naive
fix -- launch several independent Blender processes and let the OS scheduler
interleave their GPU submissions and CPU stages -- turns idle-GPU-during-CPU-
stage time in one process into overlapped work across N processes, at the
cost of some GPU contention during the (much shorter) simultaneous
path-tracing windows.

This is the standard mitigation for "Blender's CPU-heavy per-frame overhead
starves a single GPU" -- true multi-process Blender-on-one-GPU is finicky in
general (driver/VRAM contention, shared temp/cache dirs), so this launcher
does the two things that make it safe:

  1. Non-overlapping seed ranges per shard (K independent --seed/--count
     slices of the requested [seed_start, seed_start+total) range) --
     generate_synthetic.py already names each sample directory by seed, so
     disjoint seed ranges guarantee disjoint output paths with NO other
     script changes needed for "sharding".
  2. A private BLENDER_USER_CONFIG / BLENDER_USER_SCRIPTS /
     BLENDER_USER_DATAFILES / BLENDER_USER_RESOURCES / BLENDER_USER_EXTENSIONS
     / TMPDIR sandbox per shard. Blender's user-config/cache/autosave/undo
     directories are NOT designed for concurrent writers; two processes
     sharing the default ~/Library/Application Support/Blender (or
     ~/.config/blender on Linux) can race on preference or autosave writes.
     Isolating these per shard removes that failure mode entirely --
     verified empirically (see docs/RENDER_AT_SCALE.md "no cache/temp
     collisions" section).

Marketplace GPU nodes die mid-job; each shard is retried up to --max-retries
times (a fresh subprocess, same seed range -- generate_synthetic.py's
per-sample dirs make a partial shard's completed samples reusable, so a
retry just re-renders what wasn't finished/collected).

Usage:
    python3 render_farm.py --out render_farm_out --seed 0 --total 24 \\
        --shards 3 --light-variations 1 --hdri-dir /path/to/hdri_pack

    # equivalent to 3 concurrent:
    #   generate_synthetic.py --out render_farm_out --seed 0  --count 8 ...
    #   generate_synthetic.py --out render_farm_out --seed 8  --count 8 ...
    #   generate_synthetic.py --out render_farm_out --seed 16 --count 8 ...
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time

DEFAULT_BLENDER_BIN = os.path.expanduser(
    "~/Applications/Blender-5.0.1.app/Contents/MacOS/Blender"
)
DEFAULT_PYTHONPATH = os.path.expanduser("~/.local/lib/python3.11/site-packages")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SCRIPT = os.path.join(SCRIPT_DIR, "generate_synthetic.py")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", required=True, help="Shared output directory (all shards write here)")
    p.add_argument("--seed", type=int, default=0, help="First seed of the whole job's range")
    p.add_argument("--total", type=int, required=True, help="Total samples across all shards")
    p.add_argument("--shards", type=int, required=True, help="Number of concurrent Blender processes")
    p.add_argument("--light-variations", type=int, default=1)
    p.add_argument("--validate", action="store_true")
    p.add_argument("--recipe", type=str, default=None)
    p.add_argument("--hdri-dir", type=str, default=None,
                    help="Pre-fetched HDRI pack dir (see docs/RENDER_AT_SCALE.md). "
                         "Strongly recommended for >1 shard: without it every shard "
                         "independently races to download the same single HDRI file "
                         "into --out on first launch.")
    p.add_argument("--work-dir", type=str, default=None,
                    help="Where per-shard BLENDER_USER_*/TMPDIR sandboxes and logs live "
                         "(default: <out>/_farm)")
    p.add_argument("--blender-bin", type=str, default=DEFAULT_BLENDER_BIN)
    p.add_argument("--pythonpath", type=str, default=DEFAULT_PYTHONPATH)
    p.add_argument("--script", type=str, default=DEFAULT_SCRIPT)
    p.add_argument("--max-retries", type=int, default=2,
                    help="Retries per shard on nonzero exit (simulates a marketplace node dying)")
    p.add_argument("--poll-interval", type=float, default=2.0)
    return p.parse_args()


def shard_ranges(seed_start, total, shards):
    """Split [seed_start, seed_start+total) into `shards` contiguous,
    non-overlapping (seed, count) ranges. Sizes differ by at most 1 sample
    when total is not evenly divisible."""
    base, extra = divmod(total, shards)
    ranges = []
    cursor = seed_start
    for i in range(shards):
        count = base + (1 if i < extra else 0)
        if count > 0:
            ranges.append((cursor, count))
        cursor += count
    return ranges


def build_shard_env(shard_root):
    """Private Blender user-data sandbox + TMPDIR for one shard. See module
    docstring point 2 -- this is what makes concurrent Blender processes
    safe to run against a shared output directory."""
    env = os.environ.copy()
    subdirs = {
        "BLENDER_USER_CONFIG": "config",
        "BLENDER_USER_SCRIPTS": "scripts",
        "BLENDER_USER_DATAFILES": "datafiles",
        "BLENDER_USER_RESOURCES": "resources",
        "BLENDER_USER_EXTENSIONS": "extensions",
    }
    for var, sub in subdirs.items():
        d = os.path.join(shard_root, sub)
        os.makedirs(d, exist_ok=True)
        env[var] = d
    tmp = os.path.join(shard_root, "tmp")
    os.makedirs(tmp, exist_ok=True)
    env["TMPDIR"] = tmp
    if DEFAULT_PYTHONPATH not in env.get("PYTHONPATH", ""):
        env["PYTHONPATH"] = DEFAULT_PYTHONPATH + os.pathsep + env.get("PYTHONPATH", "")
    return env


def build_cmd(args, seed_start, count):
    cmd = [
        args.blender_bin, "-b", "--python-use-system-env",
        "-P", args.script, "--",
        "--out", args.out,
        "--seed", str(seed_start),
        "--count", str(count),
        "--light-variations", str(args.light_variations),
    ]
    if args.validate:
        cmd.append("--validate")
    if args.recipe:
        cmd += ["--recipe", args.recipe]
    if args.hdri_dir:
        cmd += ["--hdri-dir", args.hdri_dir]
    return cmd


def launch(args, shard_idx, seed_start, count, attempt, work_dir):
    shard_root = os.path.join(work_dir, f"shard{shard_idx}_try{attempt}")
    os.makedirs(shard_root, exist_ok=True)
    env = build_shard_env(shard_root)
    cmd = build_cmd(args, seed_start, count)
    log_path = os.path.join(shard_root, "log.txt")
    logf = open(log_path, "w")
    proc = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT, env=env)
    return {
        "shard_idx": shard_idx, "seed_start": seed_start, "count": count,
        "attempt": attempt, "proc": proc, "log_path": log_path,
        "logf": logf, "shard_root": shard_root, "t0": time.time(),
    }


def main():
    args = parse_args()
    os.makedirs(args.out, exist_ok=True)
    work_dir = args.work_dir or os.path.join(args.out, "_farm")
    os.makedirs(work_dir, exist_ok=True)

    ranges = shard_ranges(args.seed, args.total, args.shards)
    if not ranges:
        print("Nothing to do (total=0 or shards=0).")
        return

    # Pre-fetch the legacy single HDRI ONCE from the launcher before spawning
    # any shard, if no --hdri-dir was given -- avoids every shard racing to
    # download the same file into --out concurrently on a cold cache.
    if not args.hdri_dir:
        hdri_path = os.path.join(args.out, "sunflowers_1k.hdr")
        if not os.path.exists(hdri_path) and not args.validate:
            print("Pre-fetching default HDRI once (no --hdri-dir given)...")
            import requests
            url = "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/sunflowers_1k.hdr"
            r = requests.get(url)
            with open(hdri_path, "wb") as f:
                f.write(r.content)

    print(f"Sharding seeds [{args.seed}, {args.seed + args.total}) into {len(ranges)} shard(s):")
    for i, (s, c) in enumerate(ranges):
        print(f"  shard {i}: seed {s}..{s + c - 1} ({c} samples)")

    pending = [(i, s, c, 1) for i, (s, c) in enumerate(ranges)]
    running = {}
    results = {}
    t_start = time.time()

    while pending or running:
        while pending and True:
            shard_idx, seed_start, count, attempt = pending.pop(0)
            job = launch(args, shard_idx, seed_start, count, attempt, work_dir)
            running[shard_idx] = job
            print(f"[farm] launched shard {shard_idx} (attempt {attempt}), "
                  f"seeds {seed_start}..{seed_start + count - 1}, pid {job['proc'].pid}")

        finished = []
        for shard_idx, job in list(running.items()):
            rc = job["proc"].poll()
            if rc is not None:
                job["logf"].close()
                elapsed = time.time() - job["t0"]
                if rc == 0:
                    print(f"[farm] shard {shard_idx} (attempt {job['attempt']}) OK in {elapsed:.1f}s")
                    results[shard_idx] = {"ok": True, "elapsed_s": elapsed, "attempts": job["attempt"]}
                else:
                    print(f"[farm] shard {shard_idx} (attempt {job['attempt']}) FAILED "
                          f"rc={rc} after {elapsed:.1f}s -- log: {job['log_path']}")
                    if job["attempt"] < args.max_retries:
                        pending.append((shard_idx, job["seed_start"], job["count"], job["attempt"] + 1))
                    else:
                        print(f"[farm] shard {shard_idx} exhausted retries, giving up.")
                        results[shard_idx] = {"ok": False, "elapsed_s": elapsed, "attempts": job["attempt"]}
                finished.append(shard_idx)
        for shard_idx in finished:
            del running[shard_idx]

        if pending or running:
            time.sleep(args.poll_interval)

    total_elapsed = time.time() - t_start
    n_ok = sum(1 for r in results.values() if r["ok"])
    n_fail = sum(1 for r in results.values() if not r["ok"])
    print(f"\n[farm] done in {total_elapsed:.1f}s wall time. {n_ok} shard(s) OK, {n_fail} failed.")

    # Aggregate per-process timing JSON dumped by generate_synthetic.py
    # (dump_timings) so the farm's aggregate stage breakdown / throughput is
    # available without re-parsing every shard's stdout log.
    timing_files = glob.glob(os.path.join(args.out, "timings_pid*.json"))
    agg = {}
    total_script_s = 0.0
    for tf in timing_files:
        with open(tf) as f:
            payload = json.load(f)
        total_script_s += payload.get("script_total_s", 0.0)
        for k, v in payload.get("stage_totals_s", {}).items():
            agg[k] = agg.get(k, 0.0) + v

    summary = {
        "wall_time_s": round(total_elapsed, 2),
        "shards": len(ranges),
        "total_samples_requested": args.total,
        "shards_ok": n_ok,
        "shards_failed": n_fail,
        "aggregate_script_cpu_s": round(total_script_s, 2),
        "aggregate_stage_totals_s": {k: round(v, 2) for k, v in agg.items()},
        "effective_parallelism": round(total_script_s / total_elapsed, 2) if total_elapsed > 0 else None,
        "results_by_shard": results,
    }
    summary_path = os.path.join(work_dir, "farm_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"[farm] summary written to {summary_path}")
    print(json.dumps(summary, indent=2))

    sys.exit(0 if n_fail == 0 else 1)


if __name__ == "__main__":
    main()
