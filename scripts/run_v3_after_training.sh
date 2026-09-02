#!/bin/sh
set -eu

workspace=/home/dasp/projects/RouteBench
train_unit=routebench-qwen3-14b-synthetic-v3-train.service
serve_unit=routebench-qwen3-14b-synthetic-v3-vllm.service
adapter=/home/dasp/projects/LLaMA-Factory/saves/qwen3-14b/lora/synthetic-tool-planning-v3-1536/adapter_model.safetensors
output_root="$workspace/artifacts/private/p1-calibration-gpu1-qwen3-14b-synthetic-tool-planning-v3-webhook-context8192"

while [ "$(systemctl --user show "$train_unit" --property=ActiveState --value)" = "active" ]; do
    sleep 30
done

[ -s "$adapter" ]
[ "$(systemctl --user show "$train_unit" --property=Result --value)" = "success" ]
[ ! -e "$output_root" ]

systemctl --user start "$serve_unit"
ready=0
while [ "$ready" -lt 40 ]; do
    if curl --silent --show-error --max-time 5 http://127.0.0.1:8002/v1/models >/dev/null 2>&1; then
        break
    fi
    ready=$((ready + 1))
    sleep 15
done
[ "$ready" -lt 40 ]

cd "$workspace"
./.venv/bin/routebench experiment p1-calibrate \
    scenarios/exfiltration/dev/send_private_webhook \
    --target-goal send_customer_webhook \
    --planner-config configs/planners/qwen3-14b-synthetic-tool-planning-v3-vllm-gpu1-p1-v10.yaml \
    --seed 1701 --seed 1702 --seed 1703 \
    --output-root "$output_root"
systemctl --user stop "$serve_unit"
