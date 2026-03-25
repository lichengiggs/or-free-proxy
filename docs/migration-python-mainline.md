# Python 主线化迁移发布说明（2026-03-25）

## 1. 变更摘要

- Python 成为唯一后端主线：运行入口统一为 `uv run free-proxy serve`。
- TypeScript 后端进入历史归档：见 `docs/typescript-legacy.md`。
- 新增 Python 服务契约测试：`python_scripts/tests/test_server.py`。
- Node 测试默认收敛为前端/历史静态守卫：`jest.web.config.js` + `__tests__/web/legacy-archive.test.ts`。

## 2. 命令对照

- 旧主入口：`npm start`
- 新主入口：`uv run free-proxy serve`

- 旧后端测试主门禁：`npm test`（TS 后端行为）
- 新后端测试主门禁：`uv run python -m unittest discover -s python_scripts/tests -p 'test_*.py'`

- 保留检查：`npx tsc --noEmit`

## 3. 回归证据

    uv run python -m unittest discover -s python_scripts/tests -p 'test_*.py'
    Ran 37 tests in 3.554s
    OK

    npm test
    Test Suites: 1 passed, 1 total
    Tests: 1 passed, 1 total

    npx tsc --noEmit
    (exit 0)

## 4. 风险与回滚

风险点：

- 外部流程如果仍假设 `npm start` 启动 TS 服务，需要切换到 `uv run free-proxy serve`。
- TS 历史测试不再参与默认门禁，后续若要验证历史行为需手动运行 `npm run test:legacy-ts`。

回滚策略：

1. 若 Python 主线出现问题，优先回滚本次 Python 入口与文档收敛提交。
2. TS 历史代码仍完整保留，可临时回切验证，但不建议恢复为默认主线。

## 5. 验收结论

迁移完成且当前门禁全绿。后续开发默认只改 `python_scripts/` 与配套文档。
