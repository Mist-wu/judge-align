# E4 agent 审核与完成范围

2026-11-05 用户明确要求：“就按 agent 审核如实写，不做真人标注和重标，继续完成剩下的实验。” 本次 E4 因而按“自动实验 + agent 审核”范围完成；这不表示新增真人验证已完成。

- `status=complete`，`agent_review_complete=true`。
- `human_validation_complete=false`，`human_validation_required=false`。
- 新增真人标注和 50 条至少 48 小时后的真人重标：`not_requested`，没有实施。

## 审核来源与覆盖

四个 agent 分别检查 50 条单点样本和 50 对同上下文回复，合计 200 条单点（persona/quality/safety）和 200 对四维偏好。审核时隐藏了既有真人原分与模型 judge 评分，pairwise 的呈现 A/B 独立打乱；`winners_original_order` 只是映射回原顺序，原 `winners` 和 `review_A_id` / `review_B_id` 保留。

原归档为 `experiment-runner/reviews/2026-11-05/e4/`。本仓库保存完整独立副本：

- [单点审核](../results/agent-review/pointwise-reviewed.jsonl)
- [偏好审核](../results/agent-review/pairwise-reviewed.jsonl)
- [分组 0 发现](../results/agent-review/part-0-findings.md)、[分组 1](../results/agent-review/part-1-findings.md)、[分组 2](../results/agent-review/part-2-findings.md)、[分组 3](../results/agent-review/part-3-findings.md)
- [范围、覆盖与源文件 SHA-256](completion-scope.json)

600 个单点维度中 2 个为空；800 个偏好维度中 10 个不确定。32 条单点和 32 对偏好被标记，去重后为 34 个上下文。缺失参考上下文、角色版本与时间点、未明确的指代、剧情或事实前提，以及安全量表边界会影响判定；保留这些不确定项，不声称完成真人仲裁。

## 正式指标边界

CharacterEval 已发布的 200 条 Empathy 真人标签原样保留。所有新增人工字段继续为空，原始 cases/pairs、human/retest templates、judge 原始账本、模型配置、开发集选出的提示均未修改。agent 审核结果独立存放，从不传入 `--human`，也不进入既有 human gold、QWK、Spearman、人工偏好准确率、长度控制或真人重标可靠性。

原实验的 3,000 条终态、2,971 条可分析、29 条格式失败和全部正式数值不变。缺失 600 个自定义真人分、800 个真人偏好和 50 条真人重标是数据边界，不是当前待办。相应人类依赖统计继续为空；`complete` 只表示用户约定范围已完成，不代表模型可以替代真人。

报告生成器读取单独的 `completion-scope.json`，根据这批审核的 cases/pairs 内容哈希应用完成口径；不改动原模型配置哈希，不重新调用模型。
