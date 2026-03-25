# TypeScript 历史方案归档（仅供参考）

## 1. 文档定位

本文档是 `free-proxy` 的 TypeScript 后端历史档案。自 **2026-03-25** 起，项目主线实现与验收基线统一为 Python（`python_scripts/`）。

结论：

- TypeScript 方案不再作为默认运行路径。
- TypeScript 代码保留用于历史追溯与设计参考。
- 新功能与缺陷修复默认只在 Python 方案实现。

## 2. 时间线

- 早期主线：TypeScript + Hono（`src/`）。
- 迁移阶段：Python 与 TypeScript 并存，Python 补齐核心 provider、配置与服务编排。
- 当前状态（2026-03-25）：Python 成为唯一主线；TypeScript 进入历史档案。

## 3. TypeScript 历史架构速览

### 3.1 入口与路由

- 入口：`src/server.ts`
- 关键能力：
  - `POST /v1/chat/completions` 代理转发
  - `/admin/*` 与 `/api/*` 管理接口
  - OpenClaw 自动配置与备份恢复

### 3.2 配置与状态

- `src/config.ts`：`.env`/`config.json` 读写、provider key 管理、掩码与文件锁
- `src/rate-limit.ts`：限流状态持久化
- `rate-limit-state.json`：限流记录文件

### 3.3 模型发现与回退

- `src/models.ts`：多 provider 模型发现、过滤、排序
- `src/fallback.ts`：失败自动回退链路
- `src/provider-health.ts`：provider key 与模型可用性验证

### 3.4 OpenClaw 集成

- `src/openclaw-config.ts`：检测、配置、备份、恢复

## 4. Python 主线映射

| TypeScript 历史模块 | Python 主线模块 | 说明 |
|---|---|---|
| `src/server.ts` | `python_scripts/server.py` | HTTP 路由与 API 出口 |
| `src/config.ts` | `python_scripts/config.py` + `python_scripts/env_store.py` | provider 元数据、`.env` 读写 |
| `src/providers/registry.ts` | `python_scripts/provider_catalog.py` | provider 清单与元信息 |
| `src/models.ts` + `src/fallback.ts` | `python_scripts/service.py` | 模型候选排序、探测、失败回退 |
| `src/provider-health.ts` | `python_scripts/service.py` + `python_scripts/errors.py` + `python_scripts/health_store.py` | 错误分类、建议、健康状态更新 |
| `src/openclaw-config.ts` | `python_scripts/openclaw_config.py` | OpenClaw 配置与备份恢复 |
| `public/index.html` | `python_scripts/web/index.html` | 前端配置页面 |

## 5. 已确认行为差异（有意）

1. **运行命令差异**
   - 旧：`npm start`（TS 服务）
   - 新：`uv run free-proxy serve`（Python 服务）

2. **测试主门禁差异**
   - 旧：Jest + TS 后端测试是主门禁
   - 新：Python `unittest` 是主门禁；Node 测试仅保留前端/历史静态校验

3. **Longcat 模型发现策略**
   - Python 默认允许 `model_hints` 兜底，不依赖 `/models` 成功

4. **OpenClaw 测试隔离策略**
   - Python 通过 `OPENCLAW_TEST_DIR` 进行测试隔离，避免污染用户真实目录

## 6. 开发规则（历史方案）

- 禁止在 `src/` 新增业务功能。
- 如需追溯旧实现，先阅读本文档再查 `src/`。
- 若发现 Python 与历史逻辑不一致：
  1) 先写 Python 回归测试（red）
  2) 再在 Python 修复到 green
  3) 最后更新本文档“行为差异”章节

## 7. 为什么保留历史代码

- 便于排查线上历史行为来源。
- 便于对照迁移前设计决策。
- 降低一次性删除导致的回归与知识丢失风险。

保留不等于继续演进；历史代码只用于阅读，不用于主流程交付。
