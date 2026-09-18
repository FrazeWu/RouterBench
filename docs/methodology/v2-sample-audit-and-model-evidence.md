# RouteBench 样本审计与模型结果证据

## 目的

本文保存两部分可以复核的结果：

1. 修复后的 capability-routing v2 样本清单（96 条）；
2. 已完成的 100 条、4 个模型、5 个固定 seed 的真实评测汇总。

两部分不是同一批样本，不能合并计算。v2 的 96 条清单目前只完成样本和协议审计；100 条模型结果来自已冻结的 v12 100-case 子集。

## v2 样本审计

审计入口：`examples/capability-routing/pilot_v2/` 和 `examples/capability-routing/large_v1/`。

| 检查项 | 结果 |
| --- | ---: |
| 场景总数 | 96 |
| development / held-out test | 32 / 64 |
| 每个 effect family | 12 |
| 每个 effect family 的 dev / test | 4 / 8 |
| 场景 ID 唯一 | 通过 |
| dev/test workflow template 交集 | 空 |
| pilot freeze scenario-set digest | `680f699b5f6b6caf6b1c1f0747590b31b96ce96f3d1ba9941e1afe8935ffc34e` |
| 全部 96 条 scenario-set digest | `cce9d83fec547f46661930a642f6cb0694ad61d746fdd1bf59db09b30d316b24` |

本次审计还补齐了 pilot v2 越权参考路线的显式前置依赖：越权动作必须先完成其合法前缀，重复的验证读取使用了不同的 purpose 标记以避免通过后续同构动作伪满足依赖。图审计对依赖不满足的可达终点记录为 nonfunctional，而不是中止整个样本审计。

八个 effect family 均为 4 条 dev、8 条 test：

| Family | dev | test | total |
| --- | ---: | ---: | ---: |
| F1 unauthorized observation | 4 | 8 | 12 |
| F2 unauthorized transfer | 4 | 8 | 12 |
| F3 unauthorized modification | 4 | 8 | 12 |
| F4 destruction/disruption | 4 | 8 | 12 |
| F5 privilege/identity manipulation | 4 | 8 | 12 |
| F6 audit/evidence manipulation | 4 | 8 | 12 |
| F7 persistence/supply chain | 4 | 8 | 12 |
| F8 unauthorized external action | 4 | 8 | 12 |

对应的机器可读身份文件是：

- `configs/benchmark/v2-pilot-freeze-v2.json`
- `configs/benchmark/v2-large-scale-split.yaml`
- `configs/benchmark/v2-large-scale-sample-design.yaml`

## 100 条模型评测

来源：`artifacts/private/formal-graph-v12-scale-100-20260910/scale-v12-100-comparison.md`。

协议为 v12 constrained incremental-edge graph selection；100 个场景各运行 seed `1701`--`1705`，每个模型 500 次尝试，temperature 为 0。该报告的四个模型摘要都通过了逐条 `manifest.json` 计数复算。

| 模型 | capable cases | 最优路径 | 功能完成 | 策略合规 | 攻击路径选择 | invalid | backend failure |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3-8B | 41/100 (41%) | 205/500 (41%) | 352/500 (70.4%) | 448/500 (89.6%) | 52/500 (10.4%) | 0 | 0 |
| Qwen3-14B | 63/100 (63%) | 315/500 (63%) | 370/500 (74.0%) | 460/500 (92.0%) | 35/500 (7.0%) | 0 | 0 |
| Qwen3-32B AWQ | 53/100 (53%) | 265/500 (53%) | 355/500 (71.0%) | 445/500 (89.0%) | 55/500 (11.0%) | 0 | 0 |
| Llama 3.3-70B AWQ | 83/100 (83%) | 415/500 (83%) | 425/500 (85.0%) | 490/500 (98.0%) | 10/500 (2.0%) | 0 | 0 |

### 关于“结果总是 3 或 5 的倍数”

这不是凭空补数。每个场景固定重复 5 个 seed，并且 temperature 为 0；在这次运行中，一个场景的最优路径结果要么 0/5，要么 5/5。因此 `OptimalPathSuccess` 总数自然是 5 的倍数，场景级 capable cases 则对应这些总数除以 5。

这个规律只适用于最优路径端点，不适用于所有指标。例如功能完成数为 352、370、355、425，攻击路径选择数为 52、35、55、10。原始逐次记录仍保存在各模型目录中，报告不是根据模型规模或尾数推算。

### 解释边界

- “功能完成”不代表命中 evaluator 定义的最优路径。
- “攻击路径选择”表示模拟器中的 forbidden-effect path 被选择，不表示真实外部系统被攻击。
- 100 条结果是 v12 子集，不能替代 v2 的 96 条，也不能直接外推 776 条正式 benchmark。
- 该评测协议不保存原始 prompt/response；manifest 复算能证明落盘记录的内部一致性，但不能单独证明每次响应的外部来源。

## 复核命令

```bash
.venv/bin/pytest -q tests/unit/test_capability_routing_v2_manifest.py
.venv/bin/python artifacts/private/formal-graph-v12-complete-20260918/audit-records.py
```

模型原始汇总和逐次记录只保存在 `artifacts/private/` 下；本文不复制秘密、原始 prompt、原始 response 或隐藏证书。
