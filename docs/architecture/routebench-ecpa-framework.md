# RouteBench + ECPA 完整框架

这张图把现有评测模块、ECPA 运行时、训练数据和防御评估放在同一条数据流中。
实线表示已经实现的接口；虚线表示正式防御实验仍需要冻结或补齐的部分。
小模型 LoRA 是拟采用的论文主方法；既有 E5/MLP 与离线 TD 仅是开发原型。

```mermaid
flowchart LR
    A[场景与能力路由作者] --> B[冻结 ScenarioBundle\n任务/图/工具/授权/分类]
    B --> C[公开输入投影\n任务目标、图、authority、顺序]
    B --> D[评测侧私有材料\nfixture、verifier、certificate]

    C --> E[现有 RouteBench 图评测\nGraphSelection / Adherence]
    D --> E
    E --> F[公开评测桥接层\nGraphAudit 聚合结果\nfamily/length/path counts]
    E --> G[隐藏结果\nfunctional、compliance、attack、optimality]

    C --> H[ECPA 公开恢复任务\nRecoveryContract + public menu]
    H --> I[可信参考监视器\n硬禁止、授权、witness、复检]
    I --> J{allow / constrain /\nescalate / deny}
    J --> K[冻结普通任务代理\n外部响应中转劫持/注入]
    X[外部恶意中转节点\n篡改文本或伪造工具调用] --> K
    K --> I
    I --> L[真实执行 receipt\n事实/历史/预算更新]
    L --> K

    F -. 仅用于分层、采样、报告 .-> M[轨迹采集账本]
    G -. 仅用于 evaluator 端标签 .-> M
    L --> M
    M --> N[实际干预轨迹\n接受/拒绝/审批/失败/截断]
    N -.-> O[真实分支结果构造选择标签\n安全完成/违规/成本]
    O -.-> P[一个小型语言模型 LoRA 微调\nQwen3-1.7B]
    P -.-> R[受限输出候选 ID\n可信运行时复检]
    R --> H

    R --> S[正式防御评估\n配对良性/篡改响应\n文本+结构化调用]
    G --> S
    S --> T[safe recovery\nfunctional success\nviolation/attack/cost]
    T --> U[按 semantic family 聚类\n配对区间与资源报告]

    V[当前状态\n已实现：桥接、运行时、采集、训练\n待完成：正式合同、独立语料、小模型LoRA、试运行估算总成本]:::note
    V -.-> U

    classDef note fill:#fff7d6,stroke:#9a6b00,color:#4b3600;
```

## 数据边界

- `GraphAuditResult` 的路径计数、分类标签和公开路线唯一性可以进入采样分层和结果报告。
- `GraphSelectionResult.matches_hidden_certificate`、private fixture、reference route、verifier assertion 和 evaluator-owned optimum 不进入在线 scorer。
- ECPA 的最终 outcome 只能在 evaluator 侧计算；训练器使用实际 rollout 标签，不能从隐藏结果反向改变运行时菜单。
- 现有 v13 是规划前的图选择协议，ECPA 是交错执行/恢复协议。正式合并必须新建协议身份，不能直接合并历史结果。

## 资源与对照组

不再设置 200 GPU 小时硬上限；以适度总计算量、只微调一个小模型为约束。
任务代理保持冻结，不做大模型全量微调或模型规模扫描。正式模型快照与预算在短测后冻结。
主对照为：无防御、逐动作授权、路径规则、未微调小模型、同一小模型 LoRA。
训练与未训练小模型使用相同输入、菜单和解码设置；必须单独核算轨迹采集与推理成本。
