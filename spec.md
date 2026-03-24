模型字典本地化执行手册

1. Context & Vision
- 现状：线上模型数量庞大，用户和系统在选择模型时需要轮询多个候选，导致选择耗时、体验不稳定且难以保证质量。
- 改进动机：将 models.dev 索引离线化为可检索的本地字典，基于客观元信息快速过滤与排序，以减少候选集、缩短 fallback 时间并优先展示高质量模型。
- 理想状态 / 成功指标：
  - 平均候选轮询次数减少 ≥ 70%；
  - 模型选择平均延迟下降 ≥ 50%；
  - 展示给用户与后端实际调用的模型命中率（无需多次 fallback）提高；
  - 用户可见性原则：对非技术用户（小白）尽可能隐藏复杂细节，界面上仅强展示通过本地字典硬性过滤的模型；未通过过滤的模型可在 UI 中弱展示或默认折叠，由管理员/高级用户主动展开查看。

2. Core Logic (The 'What')
- 数据源：仅采集 https://models.dev/ 上公开条目；不抓取其它站点。
- 字典格式与位置：JSON 文件，路径 `data/models.dev.json`。
- 硬性过滤规则（纳入字典的最低门槛）：
  - 参数量：`params_b >= 10`（以 B 为单位整数存储，10 表示 10B）。
  - 上下文判定（精化与规则）：
    - 当 models.dev 提供细化上下文字段时优先使用：若同时存在 `input_context_limit` 与 `output_context_limit`，则将其作为硬性合格判定，默认要求为 `input_context_limit >= 100000` 且 `output_context_limit >= 10000`；
    - 在排序/评分时：仅使用 `input_context_limit`/`output_context_limit` 的数值进行上下文得分计算；`context_window` 不再用于任何判定或评分；
    - 注意：同一模型在不同 provider 上的上下文能力可能存在差异，字典条目应以 `provider_id+model_id` 作为唯一键以完整匹配各 provider 的实际能力；若在实际运行中筛选出的合格模型过少，可按产品与工程约定放宽阈值或采用降级策略。

  - 发布年：`release_year >= 2025`；
  - Tool-call 支持：必须在 models.dev 条目中标注支持 tool call（依据 models.dev 的字段/标签判定）。
- 对缺失字段的处理：若 models.dev 条目缺失关键字段（参数/上下文/发布日期），视为可能为新模型并默认保留，但在条目中标注 `field_missing: true` 以便后续人工/脚本审查。
 - 排序 / 打分策略（多因子综合评分）：
  - 将每个因子标准化为 0..1 后按权重加权求和；权重：参数 50 / 上下文 30 / 发布时间 20；按综合分降序排列。
  - 参数评分：可采用对数（log(params_b)）或线性缩放进行归一化（工程在实现阶段确定具体映射函数）。
  - 上下文评分：仅基于 `input_context_limit` 与 `output_context_limit` 的复合得分计算（例如对两项分别归一化后取加权平均）；若任一项缺失则上下文得分为 0（并保持 `field_missing` 标记）。
  - 时间评分：以 `release_year` 映射近年优先，>=2025 为最低合格年，越新得分高。
  - 可用性 Gate：保留现有实现中的可用性门（availability gate），在综合评分或最终展示前作为必要先决判断；排序逻辑应与该 gate 合并，确保不可用或明显失败的模型被降级或排除。
- 条目内容：输出条目要保留原始抓取内容（`raw`），并在条目中加入计算字段：`params_b, input_context_limit, output_context_limit, release_year, tool_support_flag, score, rank, updated_at`（缺字段时标注 `field_missing: true`）。

3. Input & Startup Behavior
- 输入（触发条件）：
  - 主数据源：models.dev 页面/接口导出的模型条目（脚本触发）；
  - 触发时点：服务启动时读取本地缓存并在后台异步触发一次更新检查（非阻塞）；管理员也可手动触发更新脚本。
- 启动时的特殊约定（开发与生产一致性）：
  - 启动时触发检查应为异步非阻塞：`npm start`/服务启动时在后台触发一次更新检查，若成功则替换本地字典并更新 `updated_at`，失败则保留旧文件并记录错误日志；
  - 开发环境要求：开发阶段至少完成一次成功的抓取（本地或 CI），以便工程能在后续实现和测试中使用有效的本地字典样本。

4. Constraints & Non-Goals
- 本任务不涉及：
  - 抓取或合并 models.dev 之外的数据源；
  - 实现运行时的在线模型选择策略（例如并发控制、分流、在线 fallback 的运行时调度细节）；
  - 做延迟或成本基准测试（可作为后续度量任务）；
  - 将数据持久化为数据库（SQLite/PG），本次仅产出 JSON 物料；如需数据库为后续议题。
- 实现边界：仅实现抓取、清洗、过滤、评分与写出本地 JSON；更新策略为启动时异步检查并按重试策略回退。

5. Acceptance Criteria (可验证的 DoD)
- AC-1 文件存在与结构：`data/models.dev.json` 存在，且所有条目包含字段：`id, name, params_b, input_context_limit, output_context_limit, release_year, license, url, tags, source, tool_support_flag, raw, score, rank, updated_at`。若缺字段则显式标注 `field_missing: true`。
 - AC-2 过滤规则生效：字典中显式包含的条目必须满足参数、发布时间与 tool 支持的硬性门槛（params_b>=10, release_year>=2025, tool_support_flag=true）；针对上下文能力：
    - 若条目同时提供 `input_context_limit` 与 `output_context_limit`，则必须满足 `input_context_limit >= 100000` 且 `output_context_limit >= 10000`；
    - 若任一或两个细化字段缺失，则该条目标记 `field_missing: true`（并保留于字典以供审查）；`context_window` 不再作为判定或替代依据；
    - 通过自动或人工抽样验证，至少 95% 的条目要么满足上述规则，要么被标注为缺失。
- AC-3 排序/评分可复现：对任意输入集合，按文档中权重（参数50/上下文30/时间20）能计算出 `score` 并按 `score` 降序生成 `rank`；工程实现需提供一个独立的计算示例（输入示例 -> 输出含 score 和 rank）。
- AC-4 启动行为与更新容错：服务在启动时能立即加载本地缓存文件并在后台异步触发一次更新；若更新网络失败，更新脚本按照“3 次重试，初始延迟 1s，倍增 2”的策略执行，最终失败时保留旧文件并在日志中记录失败原因与时间戳。
- AC-5 可审计性：每次更新写出 `updated_at`，并保留原始抓取条目 `raw`，便于人工复核与溯源；必要时能恢复到前一版本（具体存储与回滚策略在工程实现阶段确定）。

6. 执行交付清单（最小可交付项，产品视角）
- 交付物：
  1) 本规范文件（`spec.md`）；
  2) `data/models.dev.json`（示例或真实抓取结果）；
  3) 评分计算示例（JSON 输入 -> 输出含 score 和 rank），用于验收 AC-3。
- 验证步骤：
  1. 拉取或手动获取 models.dev 数据样本；
  2. 运行解析脚本产生 `data/models.dev.json`（若工程尚未实现，则手工构造样例）；
  3. 验证 AC-1..AC-5。

7. Revision Log
- 本次变更核心要点：
  1) 将原始文档内的用户批注吸收并正式化：明确 UI 可见性策略——对非技术用户隐藏复杂细节，通过硬性过滤的模型在 UI 中强展示，未通过的模型弱展示或折叠；
  2) 明确启动时的异步检查行为，并补充开发环境要求：开发阶段需至少完成一次成功抓取以便后续实现与测试；
  3) 将已有排序逻辑与本规范的评分体系合并的要求写入：保留原有可用性 gate 并在评分/排序中与其结合；
  4) 清理内联批注，统一将意图迁移到相应章节并删除原始标注。
  5) 吸收并明确化上下文能力细化要求：若存在 provider/模型级别的 input/output 限制，字典将保留这些字段并以 `provider_id+model_id` 完整匹配能力差异。
  6) 本次演进引入并确认输入/输出上下文阈值：`input_context_limit >= 100000` 且 `output_context_limit >= 10000` 为高优先级合格判定；同时彻底移除 `context_window` 的任何判定或评分角色。若在实际运行中筛选出的合格模型过少，可考虑放宽这些数值或采用降级策略（由产品与工程共同决定）。

(End of file)
