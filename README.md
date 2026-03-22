# free_proxy

[中文](README.md) | [English](README_EN.md)

聚合多家 provider 的免费层，变成一个可用的 token 池，方便个人开发与日常编码。

一句话概览：免费、易用、能足够日常OpenClaw使用。

### 免费额度一览

| 方案 | 稳定性 | 额度 | 成本 |
|---|---|---|---|
| `free_proxy` | 中 | 估算约 3.3k 次/日<br>约 100k 次/月<br>约 300USD/月等价 | 免费 |
| 美国付费 coding plan | 高 | 约 200–10,000 次/月 | 20-200USD/月 |
| 国内付费 coding plan | 高 | Lite 18,000 次/月<br>Pro 90,000 次/月 | 20-200RMB/月 |

说明：以上额度为保守估算，实际值会因 provider/地区/账号而异。阿里云百炼示例来源：https://developer.aliyun.com/article/1713813



## 核心功能（快速看）

- 聚合 8 家 provider（OpenRouter / Groq / OpenCode / Gemini / GitHub Models / Mistral / Cerebras / SambaNova）
- 自动回退：当前模型失败或限流时自动切换到可用模型
- 手动添加模型：支持 `provider+modelId` 直接添加
- 本地 Web 配置：卡片式保存 API Key，直接选模型并更新 OpenClaw
- OpenAI 兼容接口：`http://localhost:8765/v1`

## 快速开始（3 步）

1) 克隆并安装依赖

```bash
git clone https://github.com/lichengiggs/free_proxy.git
cd free_proxy
npm install
```

2) 启动

```bash
npm start
```

小白提示：`npm start` 启动后请保持这个窗口打开，不要关闭。

3) 打开配置页面并保存至少一个 provider 的 API Key

- 访问：`http://localhost:8765`
- 保存 Key 后直接选择模型开始使用

## 常见问题（简短）

- 网络错误：确认服务已启动 `npm start`，使用 `http://localhost:8765`
- 无可用模型：免费模型可能被临时限流，点“刷新模型列表”或手动添加可用模型
- API Key 存放：本地 `.env`（不会上传）

## 开发命令

```bash
# 启动
npm start

# 测试
npm test
python3 test_proxy.py

## 许可

MIT
