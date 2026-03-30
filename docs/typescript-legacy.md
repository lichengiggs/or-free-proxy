# TypeScript 历史方案归档（仅供参考）

## 1. 当前定位

- 本文档只保留历史结构说明。
- TypeScript 旧运行文件已经退出仓库运行路径。
- 当前生产主线只看 `python_scripts/`。
- 若必须追溯旧实现，请查看 git 历史，而不是恢复旧运行路径。

## 2. 历史入口与模块

历史上曾存在以下运行入口与模块：

- 入口：`src/server.ts`
- 配置：`src/config.ts`
- provider registry：`src/providers/registry.ts`
- provider router：`src/providers/router.ts`
- OpenAI adapter：`src/providers/adapters/openai.ts`
- 模型发现：`src/models.ts`
- fallback：`src/fallback.ts`
- 健康状态：`src/provider-health.ts`
- 限流与预算：`src/rate-limit.ts`、`src/request-budget.ts`
- 历史静态页面：`public/index.html`

## 3. 对应到当前 Python 主线

| 历史模块 | 当前模块 | 说明 |
| --- | --- | --- |
| `src/server.ts` | `python_scripts/server.py` | HTTP 路由与响应转换 |
| `src/config.ts` | `python_scripts/config.py` + `python_scripts/env_store.py` | `.env` 读取与写入 |
| `src/providers/registry.ts` | `python_scripts/provider_catalog.py` | provider 元数据唯一入口 |
| `src/providers/router.ts` + `src/fallback.ts` | `python_scripts/provider_routing.py` | alias 解析、候选排序、fallback 顺序 |
| `src/providers/adapters/openai.ts` | `python_scripts/provider_adapter.py` + `python_scripts/provider_transport.py` + `python_scripts/provider_errors.py` | 协议适配、传输与错误模型 |
| `src/models.ts` + `src/provider-health.ts` | `python_scripts/service.py` + `python_scripts/health_store.py` | 探测、验证、健康状态更新 |
| `src/rate-limit.ts` + `src/request-budget.ts` | `python_scripts/token_limit_store.py` + `python_scripts/token_budgeting.py` + `python_scripts/token_policy.py` | token 学习与预算 |
| `public/index.html` | `python_scripts/web/index.html` | 当前控制台页面 |

## 4. 结论

- 不再恢复 TypeScript 运行路径。
- 新功能只允许落在 Python 主线。
- 如需说明历史设计，引用本文档即可。
