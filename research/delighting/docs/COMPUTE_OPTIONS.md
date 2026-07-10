# Cloud GPU rental — decision memo for agent-driven fine-tuning

Status: research memo. Pricing verified via web search/fetch on 2026-07-10; rented GPU
markets move fast (RunPod/Vast.ai rates are live marketplaces) — treat single numbers as
"ballpark, check at launch time," not quotes.

## 1. What we're sizing for

From `reports/027-fresh-tracks.md` (Bets 1 & 2, the diffusion-prior tracks):

- **Near-term (the actual near-term need):** fine-tune a pretrained SD-1.5/SDXL-class
  latent-diffusion backbone (joint layer-separation model, or a Marigold/RGB↔X-style dense
  predictor) on our synthetic `(photo, T, h, B)` triples, 20-50k renders. Single
  A100-80GB or H100, occasionally 1-2×4090-class for smaller/cheaper runs. Wall-clock:
  hours to a few days per run. Data: tens of GB shipped up once (synthetic corpus +
  the 1,281-swatch real corpus); checkpoints (SD/SDXL UNet + LoRA weights, GB-scale)
  pulled back down or pushed to HF Hub.
- **Occasional:** batch inference/eval sweeps (assembled-pair drag test, zero-shot
  checkpoint probes) — cheap GPU is fine, short jobs, bursty.
- **Explicitly out of scope:** multi-node training, always-on serving (that's a later
  product-backend decision, not this one).
- **Controller constraint that shapes the whole memo:** the thing launching and watching
  jobs is a Claude Code agent on the maintainer's Mac. Agent sessions end (context/turn
  limits, the maintainer closing the laptop). A job that dies when the agent's shell dies
  is worthless — everything below is filtered through "can this survive the agent going
  away, and can the *next* agent find it and pull the result."

## 2. Comparison table

Prices are single-GPU, on-demand list rates unless noted. "Spot/interruptible" is the
cheapest advertised interruptible rate for the same SKU. All current as of query date
(2026-07-10); RunPod/Vast.ai/SF Compute are live marketplaces and fluctuate ±30-50%
hour to hour.

| Provider | A100-80GB on-demand | H100 on-demand | RTX 4090 | Spot/interruptible | Billing granularity | Min. commitment |
|---|---|---|---|---|---|---|
| **RunPod** | $1.39-1.49/hr | $2.89-2.99/hr | $0.34 (community) - $0.69 (secure)/hr | Community Cloud tier is itself the cheap tier (~20-40% under Secure); no separate spot market | Per-second (pods); storage per-second/hour | None — pay-as-you-go, $10 min top-up |
| **Vast.ai** | from ~$0.29/hr (unverified hosts) | ~$0.90-2.27/hr depending on host trust tier | ~$0.29-0.34/hr | "Interruptible" listings ~50%+ under on-demand | Per-second, no rounding | None |
| **Lambda Cloud** | $1.99/hr | $2.99-4.29/hr (SXM) | not offered (no consumer cards in catalog) | None — no spot/preemptible product | Per-minute | None (reserved/1-yr contracts available for lower rates, not required) |
| **Modal** | $2.50/hr ($0.000694/s) | $3.95/hr ($0.001097/s) | not offered | None (serverless autoscale substitutes for spot) | Per-second, to the function call | None; $30/mo free credit (Starter) |
| **Paperspace / DigitalOcean** | $3.18/hr | $5.95/hr | not offered | None | Hourly (Paperspace); DO droplets moved to per-second in 2026 but Paperspace GPU machines bill hourly | None |
| **Lightning.ai** | included in "GPU marketplace" tier, ~median $2.80/hr across their catalog | same marketplace, H100 listed | some listings from $0.41/hr | Interruptible listings exist in their marketplace | Per-minute-ish (credits-based) | Free tier + paid Teams plan ($1,680/mo) for heavier use — irrelevant at our scale |
| **Fal.ai** (inference-oriented) | $0.99/hr equivalent | $1.89-3.99/hr | — | — | Per-second | None; also offers "dedicated cluster" for fine-tuning at negotiated rates |
| **Replicate** (inference-oriented) | via GPU-second billing | up to $0.001525/s (~$5.5/hr) | — | — | Per-second | None |
| **SF Compute** | not sold as single-GPU | H100 **nodes** from ~$1.64-1.98/GPU/hr | — | Yes, market-priced | Per-hour, order-based | **Minimum unit is effectively a node** (8×H100), 1-hour minimum order — poor fit for single-GPU jobs |
| **AWS EC2 (p4d/p5) — reference** | p4d.24xlarge (8×A100) $32.77/hr → ~$4.10/GPU/hr | p5.48xlarge (8×H100) $55.04/hr → ~$6.88/GPU/hr | not in catalog | Spot exists on paper but P5 spot capacity is "structurally scarce" (AWS prioritizes on-demand/reserved) | Per-second | Quota approval required (see §4) |
| **GCP Compute Engine — reference** | ~$3.60-3.70/GPU/hr | ~$3.00-3.50/GPU/hr | not in catalog | Spot ~$2.25/GPU/hr for H100 (up to 91% off) | Per-second | Quota approval required (see §4) |
| **SkyPilot** | *(control layer, not a compute seller)* — provisions on any of AWS/GCP/Azure/Lambda/RunPod/Paperspace/Kubernetes/etc., picks cheapest available, handles spot preemption/recovery via managed jobs | | | | | N/A — wraps the above |

## 3. Agent-controllability, provider by provider

This is the criterion the maintainer flagged as decisive, so it gets the most words.

**RunPod** — Purpose-built GPU-pod product: you get a real Linux box with SSH, a
`runpodctl` CLI (noun-verb: `pod create/list/stop`, plus `send`/`receive` for file
transfer) and a Python SDK/REST API. Existing training scripts run unmodified — no
porting into a serverless function shape. Survival past agent-session-death is a manual
but simple discipline: SSH in, `tmux new -s train`, launch, detach; the pod is a
persistent VM so the job keeps running regardless of what happens to the controlling
terminal, and a later agent reconnects with `runpodctl` / SSH to check `tmux attach` and
pull results. Network volumes persist independently of pod lifecycle (good for the
tens-of-GB dataset shipped once + growing checkpoint dir) and cost $0.05-0.07/GB/mo with
**zero egress fees**. Scoped API keys (per-endpoint, read/write toggle) and billing
alerts (~72hr runway warning before an autopay failure kills your pods) cover the
security ask. Downside: the tmux/nohup step is a manual convention the agent must get
right every time — no platform-enforced "this job outlives you" guarantee.

**Vast.ai** — Same pod/SSH shape as RunPod (`vastai create instance --onstart-cmd ...
--ssh`, Python SDK `VastAI(api_key=...).launch_instance(...)`), but it's a raw
marketplace over individual hosts of wildly varying trust level — reliability and
performance are host-dependent, not platform-guaranteed. Great CLI ergonomics
(`pip install vastai` gets both CLI and SDK), onstart scripts up to 16KB (gzip+base64 for
more) let an agent fully script provisioning + training kickoff in one call. No built-in
job-survival primitive beyond "it's a VM, keep a session open on it" — same tmux
discipline as RunPod, with more variance in whether a given host stays up.

**Lambda Cloud** — Clean ML-tuned images (PyTorch/CUDA preinstalled), per-minute
billing, no egress fees, a documented Cloud API and a couple of community CLI wrappers
(`lambda-cloud-client`, `lambda-cloud-manager`) rather than an official first-party CLI.
Real weakness: **capacity**. Multiple 2026 reviews describe frequent on-demand sellouts
for A100/H100, one citing roughly a 64% same-day provisioning success rate over six
months. No spot/preemptible tier at all to fall back on when sold out. Fine as a backup,
risky as a primary if the maintainer wants an agent to reliably self-serve a GPU on
demand.

**Modal** — The strongest fit to the literal ask. There's no SSH/host concept at all:
you write the training job as Python (`@app.function(gpu="A100", timeout=...)`), and
`modal run --detach train.py` — the `--detach` flag is documented specifically as "don't
stop the app if the local process dies or disconnects." That is the fire-and-forget
primitive the brief asks for, built into the CLI rather than approximated with tmux.
`modal.Volume` gives persistent, mountable storage for the dataset and checkpoints
across runs; `modal.Secret` handles HF tokens / W&B keys without them touching the
agent's shell history; `modal app logs <app-id>` streams logs from any later session
(including one that has no memory of launching the job) so a fresh agent can
reattach purely from an app ID. Official examples exist for exactly this workload shape
(`modal-examples/06_gpu_and_ml/long-training.py`, a documented diffusers LoRA
fine-tune with Volume-backed checkpointing). The one real constraint: a single function
call caps at 24 hours, so a multi-day fine-tune needs checkpoint+retry
(`modal.Retries`) to chain executions — extra design work, but it's the same
checkpointing discipline you want anyway for a job running on a marketplace GPU that
could preempt. Workspace-level **hard spend caps** exist (Usage & Billing → workspace
budget) — execution stops when the cap is hit, which is the strongest built-in safety
net of anything surveyed here. Price is mid-pack, not cheapest.

**Paperspace/DigitalOcean** — Legacy Gradient CLI/API is deprecated (July 2024); DO is
mid-migration to a new Paperspace CLI/SDK (`digitalocean/gradient-python` in progress).
Hourly (not per-second/minute) billing on GPU machines. Pricing is the highest of the
self-serve providers surveyed (H100 $5.95/hr). Not recommended while the tooling
transition is unsettled.

**Lightning.ai** — Has a real Python SDK (`lightning-sdk`, a `Job` class with
`.run()`/`.status`/`.stop()`) and CLI, plus persistent storage and on-start actions —
genuinely agent-scriptable. But it's positioned as a "Studio" (interactive-first)
product with jobs as a secondary batch feature layered on top, pricing is opaque
(marketplace-ish, no clean published $/hr table, official pricing page failed to render
during this research), and the natural workflow assumes a live Studio session more than
a headless CLI-only flow. Usable, but adds product surface we don't need.

**Fal.ai / Replicate** — Both are **inference-serving** platforms first. Replicate's
training path (Cog's training API, the FLUX/DreamBooth fine-tuners) is templated around
specific model families and their own LoRA toolchains, not a place to iterate on a
bespoke joint-latent-diffusion architecture with custom losses and cross-layer
attention (Bet 1's actual design). Good, cheap answer for "run eval/inference sweeps
against a checkpoint we already have," bad fit for "write and iterate on the fine-tune
itself." Keep both in mind for the *product* inference backend later (the maintainer's
"if cloud inference is much better, I'll add a backend" comment in report 027 is about
this layer, not training).

**SF Compute** — Explicitly a **cluster-scale spot market** for teams "that think in
nodes." Self-serve VM nodes (`h100v`) exist and spin up in ~5 minutes with a real CLI
(`sf buy -d "1d" --quote`), but the product and its docs are oriented around 8-GPU node
blocks, not single-GPU rental — a mismatch for our workload size. Interesting as a cheap
option if a later phase ever needs multi-GPU, not useful for Bet 1/2 today.

**AWS/GCP spot — reference point only.** Both need an explicit GPU quota-increase
request before a new account can launch anything (AWS: 3-7 business days with written
justification, default P-instance quota is 0; GCP: up to a week, global quota that
applies account-wide). That's a hard multi-day wall before an agent can self-serve a
single GPU, which disqualifies both as the "day one" answer even though the underlying
spot pricing (GCP H100 spot ~$2.25/GPU/hr) is competitive. Keep as the fallback/reference
if a later phase needs the reliability or compliance posture of a hyperscaler.

**SkyPilot — the control-layer option, not a provider.** Open source
(`skypilot-org/skypilot`), installs as `pip install skypilot[aws,gcp,runpod,lambda,...]`,
and gives one YAML/CLI surface (`sky launch`, `sky exec`, `sky down`) over 20+ backends
including RunPod, Lambda, Paperspace, and the big clouds, with managed spot jobs that
auto-recover from preemption. This is the right layer to adopt **after** picking a
primary provider, not instead of one — it derisks provider lock-in and quota walls (if
RunPod is out of A100s, SkyPilot can fail over to Lambda or GCP spot without a rewritten
job spec) but adds a dependency and doesn't remove the underlying quota-approval problem
for the hyperscaler backends it targets. Worth wiring in once the winner's workflow is
proven, not for day one.

## 4. Ranking

1. **Best overall for agent-driven fine-tuning: Modal.** The `--detach` flag is a
   direct, documented answer to "jobs must survive the controlling session" — the
   platform enforces it, rather than the agent having to remember tmux/nohup correctly
   every time. Pure Python/CLI control surface (no SSH keys, no host-trust judgment
   calls), `Volume`-backed persistent storage, `Secret`-scoped credentials, log
   streaming reattachable from a fresh agent session by app ID alone, a documented
   diffusers-LoRA-fine-tune example matching our workload shape, and hard workspace
   spend caps. Price is mid-pack ($2.50/hr A100, $3.95/hr H100), not the cheapest.
   **RunPod is the strong runner-up** and the natural complement: cheaper, zero
   porting cost for an existing training script, and a better fit for the "occasional
   cheap batch inference/eval sweep" workload where a plain SSH box is simplest.
2. **Cheapest workable: Vast.ai.** Sub-$1/hr H100 and ~$0.29/hr 4090 are realistic on
   the interruptible/lower-trust-tier end of the marketplace; RunPod Community Cloud is
   the close, more-consistent second ($1.39-1.49/hr A100). Reserve Vast.ai for the
   "occasional batch inference/eval sweep" workload explicitly called out as
   cheap-GPU-fine, not for the primary multi-day fine-tune where host variance is a
   real risk to an unattended run.
3. **Lowest-friction first experiment: Modal, with RunPod effectively tied.** Modal:
   `pip install modal && modal setup`, write one decorated function, `modal run` — no
   GPU/host/region shopping, $30/mo free credit covers a meaningful smoke test, no
   quota approval. RunPod: self-serve signup, $10 minimum top-up, 30-60 second pod
   deploy with an SSH string handed back immediately, also no approval gate. Either is
   a same-hour path to a running GPU; Lambda and the hyperscalers are not (capacity
   sellouts / multi-day quota approval respectively).

## 5. Day-one runbook — Modal

**Maintainer does by hand (agents must never touch payment):**
1. Create a Modal account at modal.com (GitHub/Google SSO is fine), attach a payment
   method, and set a **workspace budget cap** under Usage & Billing (e.g. $150/mo to
   start — raise it after the first real run's actual cost is known).
2. Run `modal token new` once on the Mac (or `pip install modal && modal setup`) to
   mint the local API token — this is the credential that must stay out of agent hands
   beyond "already configured in this shell's environment." Do not paste the token
   into a prompt to an agent; let `modal setup` write it to `~/.modal.toml` directly.
3. Create scoped secrets the training job will need, e.g.
   `modal secret create huggingface HF_TOKEN=hf_xxx` (a **write-scoped, HF-only**
   token, not the maintainer's full HF account token) so a fine-tuned checkpoint can be
   pushed to a private HF Hub repo as the artifact-retrieval path.
4. Optionally enable 2FA on both Modal and the HF account tied to that token.

**Agent then does (headless, from this Claude Code environment):**
1. `pip install modal` in the project venv; confirm `modal token new` already ran
   (skip token creation — that's the maintainer's step).
2. Write the fine-tune as a Modal `App`/`Function`: `gpu="A100-80GB"` (or `"H100"`),
   `timeout=` up to 86400s, `volumes={"/data": modal.Volume.from_name("vitraux-delight",
   create_if_missing=True)}` for the synthetic corpus (upload once via `modal volume
   put`) and for checkpoints; `secrets=[modal.Secret.from_name("huggingface")]`.
   Bake checkpoint-then-push-to-HF-Hub as the last step of every N training steps so a
   preempted/timed-out run has an artifact already off-box.
3. Launch fire-and-forget: `modal run --detach train.py::train`. Note the returned
   app ID.
4. Monitor from any later session with `modal app logs <app-id>` (or the Modal
   dashboard URL, which is safe to hand to the maintainer to watch passively).
5. Pull results: either `modal volume get vitraux-delight checkpoints/ ./local-dir`
   or — preferred for durability — treat the HF Hub push in step 2 as the artifact of
   record, so a follow-up agent with zero memory of the run can `huggingface_hub`
   download the final checkpoint regardless of whether the Modal volume is still
   around.
6. For multi-day runs: wrap the training loop so it resumes from the latest Volume
   checkpoint on (re)start, and set `modal.Retries(max_retries=N)` so a 24-hour
   timeout or a preemption chains into a fresh execution rather than silently dying.

**Estimated cost:**
- **One Bet-1 fine-tune (~24 GPU-hours, A100-class):** 24 × $2.50/hr ≈ **$60** on
  Modal A100-80GB. (For comparison: ≈$36 on RunPod A100 SXM at $1.49/hr, ≈$24-36 on
  Vast.ai depending on host tier — Modal costs roughly 1.7-2.5× RunPod/Vast for the
  same GPU-hours, which is the premium being paid for the `--detach`/Volume/Secret
  ergonomics and the hard spend cap.)
- **100-hour experimentation month** (mix of the above plus eval sweeps, call it 100
  GPU-hours blended across A100 and cheaper spot/4090 runs): roughly **$150-250** on
  Modal if run entirely on A100; realistically less if eval sweeps are pushed to
  RunPod/Vast 4090 instances at $0.30-0.70/hr as the brief intends ("cheaper GPU
  fine" for batch inference/eval). A reasonable blended monthly budget to set as the
  Modal workspace cap: **$300**, leaving headroom for a bad run or a retry storm.

## 6. Security hygiene

- **Never let an agent handle payment.** Account creation, card entry, and the
  workspace/monthly spend cap are maintainer-only steps on every provider surveyed.
- **Scope API keys/tokens to the minimum needed.** RunPod supports per-endpoint scoped
  keys with read/write toggles; Modal secrets are per-workspace and can be scoped to
  what a given function needs (e.g., an HF token with write access to exactly one repo,
  not the maintainer's full account). Vast.ai's API key is currently more monolithic —
  treat it as high-value and rotate it if it will live in an agent-accessible
  environment for an extended period.
- **Spend limits/alerts, ranked by how real the guarantee is:** Modal's workspace
  budget is a hard cap — execution stops when hit. RunPod's billing alerts are an
  early-warning system (~72hr notice before autopay failure), not a hard stop — a
  runaway job can still burn through more than expected before the account is
  suspended. Vast.ai, Lambda, and Paperspace did not surface any first-party
  spend-cap feature in this research; for those, the mitigation is the agent
  self-limiting job duration/GPU count in the job template itself, and the maintainer
  checking the dashboard periodically.
- **Rotate the token if an agent transcript could have echoed it.** Prefer secrets
  managers/`.env` files outside of what gets pasted into a prompt; Modal's
  `modal secret create` and RunPod's env-var injection both keep the actual value out
  of command-line arguments that might get logged.

## 7. Surprises worth flagging to the maintainer

- **SF Compute is not sized for us.** It reads on paper like a natural "spot
  marketplace" pick, but it's explicitly a cluster/node-scale market (documented
  minimum unit is effectively an 8×H100 node); there's no clean single-GPU self-serve
  path. Cross it off for this project.
- **Lambda's headline pricing is good but availability is the real cost.** Reviews
  through 2026 still describe on-demand A100/H100 sellouts (one citing ~64% same-day
  success over six months) and Lambda has no spot/preemptible fallback tier at all —
  when it's sold out, there's no cheaper-but-slower option to fall back to the way
  there is on RunPod/Vast/GCP.
- **AWS/GCP quota approval is a real multi-day wall for a brand-new account**, not a
  formality — AWS default P-instance quota is 0 vCPUs and the increase request wants a
  written justification with a 3-7 business day turnaround; GCP is similar (up to a
  week). Neither is viable as a "day one" path regardless of how good their spot
  pricing looks on a table.
- **RTX 4090 is missing from the "serious" providers' catalogs entirely** — Lambda,
  Modal, and Paperspace don't offer it at all (their whole catalog skews A100/H100/B200
  enterprise cards). It only shows up on the marketplace-style providers (RunPod, Vast,
  Lightning's marketplace), which is fine for us since that's also where it's cheapest.
- **Paperspace's tooling is mid-migration** — the old Gradient CLI/API was deprecated
  in mid-2024 and the DigitalOcean-native replacement (`gradient-python`) is still
  being built out. Combined with hourly (not per-second) billing and the highest prices
  surveyed, there's no reason to route around this for our use case.
- **Modal's `--detach` flag is a closer literal match to the brief's requirement than
  anything else surveyed** — every other provider's answer to "survive the controlling
  session" is "it's a persistent VM, use tmux," which works but is a convention the
  agent must get right every time rather than something the platform enforces.

## Sources

- [RunPod pricing](https://www.runpod.io/pricing) · [RunPod pods pricing docs](https://docs.runpod.io/pods/pricing) · [RunPod scoped API keys](https://www.runpod.io/blog/scoped-api-keys-runpod) · [RunPod tmux docs](https://docs.runpod.io/tips-and-tricks/tmux) · [runpod Python SDK](https://github.com/runpod/runpod-python) · [runpodctl](https://github.com/runpod/runpodctl)
- [Vast.ai pricing](https://vast.ai/pricing) · [Vast.ai pricing docs](https://docs.vast.ai/documentation/instances/pricing) · [Vast.ai CLI hello world](https://docs.vast.ai/cli/hello-world) · [Vast.ai Python SDK](https://vast.ai/developers/sdk)
- [Lambda pricing](https://lambda.ai/pricing) · [Lambda instance docs](https://docs.lambda.ai/public-cloud/on-demand/creating-managing-instances/) · [Lambda Labs review 2026](https://www.gpucloudlist.com/en/blog/lambda-labs-review-2026) · ["Why I stopped using Lambda Labs"](https://medium.com/@velinxs/why-i-stopped-using-lambda-labs-for-gpu-cloud-5c59cabc5c43)
- [Modal pricing](https://modal.com/pricing) · [Modal timeouts docs](https://modal.com/docs/guide/timeouts) · [Modal long-training example](https://modal.com/docs/examples/long-training) · [Modal diffusers LoRA fine-tune example](https://modal.com/docs/examples/diffusers_lora_finetune) · [Modal secrets](https://modal.com/docs/guide/secrets) · [Modal billing docs](https://modal.com/docs/guide/billing) · [modal run CLI reference](https://modal.com/docs/reference/cli/run)
- [Paperspace pricing](https://www.paperspace.com/pricing) · [Gradient CLI deprecation](https://github.com/Paperspace/gradient-cli/blob/master/README.md) · [DigitalOcean per-second billing](https://docs.digitalocean.com/products/droplets/details/pricing/)
- [Lightning AI pricing](https://lightning.ai/pricing/) · [Lightning SDK](https://pypi.org/project/lightning-sdk/) · [Lightning CLI docs](https://lightning.ai/docs/overview/cli)
- [fal.ai pricing](https://fal.ai/pricing) · [Replicate pricing](https://replicate.com/pricing) · [Replicate training docs](https://github.com/replicate/cog/blob/main/docs/training.md)
- [SF Compute](https://sfcompute.com/) · [SF Compute prices](https://sfcompute.com/prices) · [SF Compute market docs](https://docs.sfcompute.com/docs/how-the-market-works)
- [AWS EC2 spot pricing](https://aws.amazon.com/ec2/spot/pricing/) · [AWS EC2 on-demand pricing](https://aws.amazon.com/ec2/pricing/on-demand/)
- [GCP Spot VM pricing](https://cloud.google.com/spot-vms/pricing) · [GCP GPU pricing](https://cloud.google.com/compute/gpus-pricing) · [GCP quota docs](https://cloud.google.com/compute/resource-usage)
- [SkyPilot GitHub](https://github.com/skypilot-org/skypilot) · [SkyPilot managed jobs docs](https://docs.skypilot.co/en/v0.6.0/examples/managed-jobs.html) · [SkyPilot quota docs](https://docs.skypilot.co/en/latest/cloud-setup/quota.html)
