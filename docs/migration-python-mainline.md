# Python 主线化迁移发布说明（2026-03-30）

## 当前状态

- Python 是仓库唯一运行入口。
- 启动命令统一为：`uv run free-proxy serve`
- 默认验收命令：
  - `uv run python -m unittest discover -s python_scripts/tests -p 'test_*.py'`
  - `npm test -- --runInBand`
  - `npx tsc --noEmit`

## 对外稳定接口

- `GET /v1/models`
- `POST /v1/chat/completions`
- 公共稳定模型别名：
  - `free-proxy/auto`
  - `free-proxy/coding`

## 本次收口结果

- Provider 元数据只保留 `python_scripts/provider_catalog.py`
- 路由策略下沉到 `python_scripts/provider_routing.py`
- 上游适配拆分为：
  - `python_scripts/provider_errors.py`
  - `python_scripts/provider_transport.py`
  - `python_scripts/provider_adapter.py`
- `python_scripts/service.py` 只保留状态、预算、执行编排
- `python_scripts/server.py` 只保留 HTTP 路由与响应转换

## 已移除的历史运行路径

旧的 TypeScript runtime 与附属脚本已经退出运行路径，只保留历史文档说明，不再参与启动、测试或决策。

## 历史资料

- TypeScript 历史档案：`docs/typescript-legacy.md`
- 当前结构说明：`docs/research.md`
