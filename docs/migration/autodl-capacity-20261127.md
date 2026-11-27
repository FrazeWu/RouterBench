# AutoDL resource estimate, 2026-11-27

The task is repeated inference and simulator/search evaluation. The single
seed-29 LoRA fit has already completed and should be reused after verification.
A large new training cluster is unnecessary.

The default restart repeats the fixed supplemental matrix: E1 11,640 planning
attempts; E2 168 development and 1,680 formal units; dynamic B--E 1,920 new
attempts with 480 identical A attempts reused from the new E1; and E4/E5/E6
200 + 164 + 984 = 1,348 recovery episodes. E9 and E7 are primarily CPU work.
Existing historical studies and the verified original E3 are archived, not
silently relabelled as new runs. Repeating original E3 as well adds 1,000
recovery episodes, without requiring a new fit.

## Memory and machine size

The observed Qwen3-14B model load consumes about 27.52 GiB of GPU memory. The
32,768-token graph server reported another 7.62 GiB of allocated KV cache
(49,904 token capacity) plus activations/runtime. Its actual reservation was
about 36 GiB. A conventional 24 GB RTX 4090 cannot hold these BF16 weights,
let alone the original context. A single 32 GB RTX 5090 also lacks margin for
this model's original 32K context; two cards require tensor-parallel placement
and a newly frozen binding. Aggregate VRAM is not automatically shared.

A 48 GB task GPU is a practical lower-memory option. A single 80 GB A800 can
hold the task model and compact selector together with an explicit memory
partition, avoiding a mostly idle second GPU. The existing software requires
single-card adaptation first: it hardcodes two logical devices, one task server
on GPU 1 and a selector on GPU 0. The 48 GB option needs tighter reservations.
A 96 GB PRO 6000 has comfortable memory but changes GPU architecture and needs
its own driver/backend smoke checks. Two 80 GB A800 cards preserve the original
separate task/selector layout and make independent graph jobs easier to shard.

Recommend 16 or more allocated vCPUs, 128 GB RAM (64 GB is the lower practical
starting point for serial loads), and a 200 GB data disk plus 40--60 GB system
disk. The three base snapshots occupy about 45--47 GiB; environments, Git,
archives and expanded logs need additional space. Pick local SSD storage and
check the CPU/RAM actually assigned to the instance.

## Reference prices and budget assumptions

AutoDL's official public homepage listed A800-80GB at CNY 5.59/card/hour,
PRO 6000 96GB at 8.36, H800 80GB at 9.98, RTX 5090 32GB at 2.78 and ordinary
RTX 4090 24GB at 1.88 when its public page was retrieved for this estimate.
These are public reference listings, not authenticated live inventory or a
reserved quote. Region, GPU specification, membership and current offers can
change the checkout price. Storage and network extras are not included below.

| Configuration | Budgeted instance wall time | GPU hours | Reference GPU charge |
|---|---:|---:|---:|
| 1 x A800 80GB, after single-card adaptation | 48--96 h | 48--96 | CNY 268--537 |
| 2 x A800 80GB, serial original layout | 48--96 h | 96--192 | CNY 537--1,073 |
| 2 x A800 80GB, prospectively fixed parallel graph shards | 36--72 h | 72--144 | CNY 402--805 |
| 1 x PRO 6000 96GB, single-card adaptation | use 48--96 h until measured | 48--96 | CNY 401--803 |

Prefer one A800 80GB for cost if a clean single-card migration is acceptable;
prefer two A800 80GB for the straightforward two-device layout. AutoDL also
lists 4090-48G, 3090-48G and H800-80G specifications; 48 GB variants are different
products from an ordinary 24 GB 4090. Compare their actual price and memory
before selecting them. There is no need to rent 8 GPUs for this matrix.

These times are planning ranges, not measurements on rented GPUs. The completed
local Qwen3-14B E1 block acquired 3,880 attempts / 14,364 requests / 55,712,417
charged tokens in 8.18 wall hours; the recorded HTTP model-call durations summed
to only 2.32 hours. Therefore, changing peak GPU TFLOPS cannot scale total wall
time directly: pacing, cooling, simulation, CPU, durable writes and startup
account for much of this local observation. Reboots and malformed final summary
status also limit comparisons. The ECPA protocol includes a two-second request
gap, so faster GPUs cannot eliminate that fixed component. Parallel speedups
require a changed scheduler and a protocol frozen before model outcomes.

Allow a further 20--30% cash margin for downloads, compatibility checks and
uncertainty; for one A800, a practical initial budget is approximately CNY
350--650. If original E3 is also rerun, reserve roughly 12--36 additional
instance hours as a sensitivity allowance and update the budget after a
non-outcome engineering timing check. No extra collection or training is implied.

Sources: [AutoDL official public price listings](https://backup.autodl.com/),
[AutoDL GPU selection and per-card CPU/RAM allocation](https://www.autodl.com/docs/gpu),
[AutoDL specification IDs, including 4090-48G](https://autodl.com/docs/instance_pro_api/),
[AutoDL performance caveats](https://api.autodl.com/docs/gpu_perf/),
[AutoDL billing policy: current website price governs](https://api.autodl.com/docs/price/).
