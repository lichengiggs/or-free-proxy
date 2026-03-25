# AGENTS.md

## 项目经验总结

### 1. 架构原则

**最小有效剂量**：只实现当前必需的功能，不为假设的未来场景做过度设计。

**做完即收尾**：事情完成后直接结束，不额外延伸无关步骤或多余思考；沟通也保持最小有效剂量。

**KISS 原则**：保持简单。复杂的抽象层往往比直接代码更难维护。

### 2. 本次开发教训

#### API Key 管理
- 存储位置：`.env` 放在项目根目录（而非 home 子目录），便于测试和用户理解
- 安全：绝不在 Git 中提交真实 key，`.gitignore` 必须包含 `.env`

#### OpenClaw 配置
- 路径：使用 `~/.openclaw/openclaw.json`（绝对路径）
- 检测失败时：提供手动输入路径的选项
- 备份：修改前自动创建时间戳备份

#### 模型可用性
- 不要信任 OpenRouter 返回的免费模型列表
- 后端仍保留可用性判断和 fallback 兜底
- 前端不要把“验证”做成阻塞式必经步骤，直接选择更符合当前 UI 体验
- 候选池：内存中维护，启动时验证 + 用户手动刷新

#### 测试策略
- TDD 是好习惯，但测试文件要和实现同步更新
- 模拟外部 API 时，测试期望要和实际 HTTP 状态码一致

### 3. 代码规范

**不要：**
- 添加不必要的 JSDoc 注释
- 使用 `any` 类型
- 过度工程化的抽象层

**要：**
- 注释解释 "Why" 而非 "What"
- 强制处理边界条件（null、空数组、网络错误）
- 错误信息对小白友好（不暴露技术细节）

### 4. 调试技巧

```bash
# 检查端口占用
lsof -i :8765

# 查看服务日志
npm start 2>&1 | tail -50

# 测试 API
curl -X POST http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"auto","messages":[{"role":"user","content":"hi"}]}'
```

### 5. 安全检查（推送 GitHub 前必做）

```bash
# 1. 清理本地敏感文件
rm -f  config.env config.json rate-limit-state.json

# 2. 检查待提交文件
git status

# 3. 扫描历史记录中的 API key
git log --all -p | grep -E "sk-or-[a-zA-Z0-9]{40,}"

# 4. 检查源代码中是否硬编码了 key
grep -r "sk-or-" src/ __tests__/ public/ --include="*.ts" --include="*.html" --include="*.js"

# 5. 确认 .gitignore 包含敏感文件
cat .gitignore | grep -E "\.env|config\.json"

# 6. 使用 trufflehog 深度扫描（可选）
trufflehog git file://. --only-verified 2>/dev/null || echo "trufflehog 未安装"
```

**如果发现问题：**
- 立即停止推送
- 删除包含敏感信息的提交（`git rebase -i` 或 `git filter-repo`）
- 在 OpenRouter 删除泄露的 key 并重新生成

### 6. 发布 checklist

- [ ] 运行安全检查（第 5 节所有步骤）
- [ ] 更新 README.md
- [ ] 做 git 提交前先把 `research.md` 更新到最新状态
- [ ] 运行 `npm test`（确保不报错）
- [ ] 运行 `npx tsc --noEmit`（类型检查通过）
- [ ] 清理中间文档（plan.md 等）；`research.md` 需保留并保持最新
- [ ] 推送前最后确认：`git diff --stat`

### 7. 文档维护约定
执行计划 (ExecPlans)
在编写复杂功能或进行重大重构时，请参考 `.agent/PLANS.md` 中的说明，在从设计到实现的整个过程中使用执行计划 (ExecPlan)。
