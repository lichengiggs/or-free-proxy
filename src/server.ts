import { serve } from '@hono/node-server';
import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { serveStatic } from '@hono/node-server/serve-static';
import { stream } from 'hono/streaming';
import { getConfig, setConfig, ENV, fetchWithTimeout, saveApiKey, getApiKeyStatus, getProviderKey, saveProviderKey, getAllProviderKeysStatus, saveCustomProvider, saveCustomModel, getCustomModels, deleteCustomModel } from './config';
import { fetchModels, filterFreeModels, rankModels, fetchAllModels, normalizeProviderModels, clearModelDiscoveryCache } from './models';
import { executeWithFallback } from './fallback';
import { detectOpenClawConfig, mergeConfig, listBackups, restoreBackup } from './openclaw-config';
import { PROVIDERS, isKnownProvider } from './providers/registry';
import { validateProviderKey, validateProviderKeyWithKey, verifyModelAvailability, type VerifyReason, buildProviderHeaders, normalizeVerificationModelId } from './provider-health';

const app = new Hono();

export { app, getConfig, setConfig };

// CORS 配置
app.use('/*', cors({
  origin: (origin) => {
    if (!origin) {
      return 'http://localhost:8765';
    }
    if (origin.startsWith('http://localhost:') || origin.startsWith('http://127.0.0.1:') || origin === 'null') {
      return origin;
    }
    return 'http://localhost:8765';
  }
}));

// 静态文件服务
app.use('/*', serveStatic({
  root: './public',
  index: 'index.html'
}));

// 解析模型 ID，返回 provider 和实际模型名
function parseModelId(modelId: string): { provider: string; model: string } {
  const parts = modelId.split('/');
  if (parts.length >= 2 && isKnownProvider(parts[0])) {
    return { provider: parts[0], model: parts.slice(1).join('/') };
  }
  // 默认使用 openrouter
  return { provider: 'openrouter', model: modelId };
}

const PROVIDER_CONFIGS: Record<string, { baseURL: string; apiKeyEnv: string }> = Object.fromEntries(
  PROVIDERS.map(provider => [
    provider.name,
    {
      baseURL: provider.name === 'openrouter' ? ENV.OPENROUTER_BASE_URL : provider.baseURL,
      apiKeyEnv: provider.apiKeyEnv
    }
  ])
);

function getProviderConfig(provider: string) {
  return PROVIDER_CONFIGS[provider];
}

function buildUpstreamRequest(provider: string, baseURL: string, model: string, body: any): { url: string; payload: unknown } {
  if (provider === 'gemini') {
    return {
      url: `${baseURL}/${normalizeVerificationModelId(provider, model)}:generateContent`,
      payload: {
        contents: Array.isArray(body.messages)
          ? body.messages.map((message: { role?: string; content?: unknown }) => ({
            role: message.role === 'assistant' ? 'model' : 'user',
            parts: [{ text: typeof message.content === 'string' ? message.content : JSON.stringify(message.content ?? '') }]
          }))
          : [{ parts: [{ text: 'ping' }] }],
        generationConfig: {
          maxOutputTokens: Number.isFinite(body.max_tokens) ? body.max_tokens : 16,
          temperature: typeof body.temperature === 'number' ? body.temperature : undefined
        }
      }
    };
  }

  return {
    url: `${baseURL}/chat/completions`,
    payload: {
      ...body,
      model: normalizeVerificationModelId(provider, model)
    }
  };
}

function sanitizeOutgoingHeaders(provider: string, headers: Record<string, string>): Record<string, string> {
  const sanitized: Record<string, string> = {};

  const forwarded = ['accept', 'accept-language'];
  for (const header of forwarded) {
    const value = headers[header];
    if (value) sanitized[header] = value;
  }

  if (provider === 'openrouter') {
    const userAgent = headers['user-agent'];
    if (userAgent) sanitized['user-agent'] = userAgent;
  }

  return sanitized;
}

function verifyReasonToMessage(reason?: VerifyReason): string | undefined {
  if (!reason) return undefined;
  if (reason === 'auth_failed') return 'API key 无效或权限不足';
  if (reason === 'network_error') return '网络连接失败，请检查网络或代理设置';
  return '模型不可用或当前 provider 暂不可用';
}

function mapGeminiFinishReason(reason?: string): string {
  if (reason === 'MAX_TOKENS') return 'length';
  if (reason === 'SAFETY') return 'content_filter';
  return 'stop';
}

function transformGeminiResponse(data: any, modelId: string) {
  const candidates = Array.isArray(data?.candidates) ? data.candidates : [];

  return {
    id: data?.responseId || `gemini-${Date.now()}`,
    object: 'chat.completion',
    created: Math.floor(Date.now() / 1000),
    model: data?.modelVersion || modelId,
    choices: candidates.map((candidate: any, index: number) => ({
      index,
      finish_reason: mapGeminiFinishReason(candidate?.finishReason),
      message: {
        role: 'assistant',
        content: Array.isArray(candidate?.content?.parts)
          ? candidate.content.parts
              .map((part: any) => typeof part?.text === 'string' ? part.text : '')
              .join('')
          : ''
      }
    })),
    usage: {
      prompt_tokens: Number(data?.usageMetadata?.promptTokenCount || 0),
      completion_tokens: Number(data?.usageMetadata?.candidatesTokenCount || 0),
      total_tokens: Number(data?.usageMetadata?.totalTokenCount || 0)
    }
  };
}

const verificationStatus = new Map<string, { verified: boolean; reason?: VerifyReason; lastCheckedAt: number; pending?: boolean }>();
let verifyingInBackground = false;

function startBackgroundModelVerification(models: Array<{ id: string; provider: string }>): void {
  if (verifyingInBackground) return;
  const pending = models.filter(model => {
    const status = verificationStatus.get(model.id);
    return !status || Date.now() - status.lastCheckedAt > 10 * 60 * 1000;
  });
  if (!pending.length) return;

  for (const model of pending) {
    verificationStatus.set(model.id, {
      verified: false,
      pending: true,
      lastCheckedAt: Date.now()
    });
  }

  verifyingInBackground = true;
  void (async () => {
    try {
      for (const model of pending) {
        const parsed = parseModelId(model.id);
        const availability = await verifyModelAvailability(parsed.provider, parsed.model);
        verificationStatus.set(model.id, {
          verified: availability.verified,
          reason: availability.reason,
          lastCheckedAt: availability.lastCheckedAt,
          pending: false
        });
      }
    } finally {
      verifyingInBackground = false;
    }
  })();
}

// 1. Chat Completions 接口
app.post('/v1/chat/completions', async (c) => {
  try {
    const body = await c.req.json();
    const headers = Object.fromEntries(
      Array.from(c.req.raw.headers.entries()).map(([key, value]) => [key.toLowerCase(), value])
    );
    const config = await getConfig();
    const preferredModel = typeof body?.model === 'string' && body.model.trim().length > 0
      ? body.model
      : config.default_model;

    const result = await executeWithFallback(
      preferredModel,
      async (modelToTry) => {
        const { provider, model } = parseModelId(modelToTry);
        const providerConfig = getProviderConfig(provider) || (() => {
          return undefined;
        })();
        const customProvider = !providerConfig
          ? (await getConfig()).customProviders?.find(p => p.name === provider)
          : undefined;
        const dynamicProviderConfig = providerConfig || (customProvider
          ? { baseURL: customProvider.baseURL, apiKeyEnv: '' }
          : undefined);
        
        if (!dynamicProviderConfig) {
          return { success: false, error: { message: `Unknown provider: ${provider}` } };
        }

        const apiKey = providerConfig
          ? process.env[providerConfig.apiKeyEnv]
          : customProvider?.apiKey;
        if (!apiKey) {
          return { success: false, error: { message: `API key not configured for ${provider}` } };
        }

        const proxyHeaders: Record<string, string> = {
          ...buildProviderHeaders(provider, apiKey),
          ...sanitizeOutgoingHeaders(provider, headers)
        };

        const upstream = buildUpstreamRequest(provider, dynamicProviderConfig.baseURL, model, body);

        try {
          const response = await fetchWithTimeout(
            upstream.url,
            {
              method: 'POST',
              headers: proxyHeaders,
              body: JSON.stringify(upstream.payload)
            },
            60000
          );

          if (response.ok) {
            return { success: true, response };
          }

          const errorBody = await response.text();
          return {
            success: false,
            error: {
              status: response.status,
              message: errorBody,
              retry_after: response.headers.get('retry-after') ? parseInt(response.headers.get('retry-after')!) : undefined
            }
          };
        } catch (err: any) {
          return { success: false, error: { message: err.message } };
        }
      }
    );

    const response = result.result;
    const fallbackInfo = result.fallbackInfo;

    c.header('X-Actual-Model', fallbackInfo.model);
    if (fallbackInfo.is_fallback) {
      c.header('X-Fallback-Used', 'true');
      c.header('X-Fallback-Reason', fallbackInfo.fallback_reason || 'Primary model unavailable');
    }

    if (body.stream) {
      const responseHeaders = Object.fromEntries(response.headers.entries());
      c.status(response.status as any);
      Object.entries(responseHeaders).forEach(([key, value]) => {
        if (key.toLowerCase() !== 'content-encoding') {
          c.header(key, value);
        }
      });

      return stream(c, async (stream) => {
        if (!response.body) return;
        const reader = response.body.getReader();
        let done = false;
        while (!done) {
          const chunk = await reader.read();
          done = chunk.done;
          if (!done && chunk.value) await stream.write(chunk.value);
        }
      });
    }

    const data = await response.json();
    const actualProvider = parseModelId(fallbackInfo.model).provider;
    const normalized = actualProvider === 'gemini'
      ? transformGeminiResponse(data, fallbackInfo.model)
      : data;
    return c.json(normalized, { status: response.status as any });

  } catch (err: any) {
    console.error(`[${new Date().toISOString()}] Request error:`, err.message);
    const message = String(err?.message || 'internal error');
    const isCreditsIssue = /insufficient credits|402/i.test(message);
    const isFreeDailyLimit = /free-models-per-day|429/i.test(message);

    const hint = isCreditsIssue
      ? 'OpenRouter 账号 credits 不足，请充值或切换其他 provider。'
      : isFreeDailyLimit
        ? 'OpenRouter 免费模型日额度已用完，请等待重置或充值。'
        : '请检查 provider key、网络连接或切换模型重试。';

    const status = isCreditsIssue ? 402 : isFreeDailyLimit ? 429 : 500;

    return c.json({
      error: {
        message,
        hint,
        type: 'internal_error',
        code: status
      }
    }, status as 402 | 429 | 500);
  }
});

// 2. 获取模型列表（直接返回所有可用模型，不验证）
app.get('/admin/models', async (c) => {
  try {
    // 检查是否有任何 provider 配置了 API Key
    const { getAllProviderKeysStatus } = await import('./config');
    const keyStatus = await getAllProviderKeysStatus();
    const hasAnyKey = Object.values(keyStatus).some(s => s.configured);
    
    if (!hasAnyKey) {
      return c.json({
        models: [],
        current: 'none',
        recommended: null,
        total_available: 0,
        message: '请先配置至少一个 Provider 的 API Key'
      });
    }
    
    const shouldRefresh = c.req.query('refresh') === 'true';
    if (shouldRefresh) {
      clearModelDiscoveryCache();
    }

    // 直接从所有 provider 获取模型列表
    const allModels = await fetchAllModels();
    const githubModels = allModels.filter(m => m.provider === 'github');
    const opencodeModels = allModels.filter(m => m.provider === 'opencode');
    
    // 过滤免费模型
    const freeModels = allModels.filter(m => {
      // OpenCode 特殊处理：只保留带 -free 后缀的模型
      if (m.provider === 'opencode') {
        return m.id.endsWith('-free') || m.id.includes('-free-');
      }

      const providerMeta = PROVIDERS.find(p => p.name === m.provider);

      // 除 OpenRouter 外，标记为免费 provider 的模型默认展示
      if (m.provider !== 'openrouter' && providerMeta?.isFree) {
        return true;
      }
      
      // 其他 provider：按 pricing 判断
      const prompt = parseFloat(String(m.pricing?.prompt || '0'));
      const completion = parseFloat(String(m.pricing?.completion || '0'));
      return prompt === 0 && completion === 0;
    });

    const hasOpenRouterEntry = freeModels.some(model => model.id === 'openrouter/auto:free');
    if (!hasOpenRouterEntry) {
      freeModels.unshift({
        id: 'openrouter/auto:free',
        name: 'openrouter/auto:free',
        provider: 'openrouter',
        pricing: { prompt: '0', completion: '0' }
      });
    }

    if (!freeModels.some(m => m.provider === 'github') && githubModels.length) {
      const preferred = githubModels.find(m => m.id.includes('gpt-4o-mini')) || githubModels.find(m => m.id.includes('gpt-4o')) || githubModels[0];
      if (preferred) freeModels.push(preferred);
    }

    if (!freeModels.some(m => m.provider === 'opencode') && opencodeModels.length) {
      const preferred = opencodeModels.find(m => m.id.includes('free')) || opencodeModels[0];
      if (preferred) freeModels.push(preferred);
    }

    if (!freeModels.some(m => m.provider === 'opencode')) {
      freeModels.push({
        id: 'opencode/mimo-v2-pro-free',
        name: 'MiMo V2 Pro Free',
        provider: 'opencode',
        pricing: { prompt: '0', completion: '0' }
      });
    }

    if (shouldRefresh) {
      verificationStatus.clear();
    }
    startBackgroundModelVerification(freeModels);
    
    const config = await getConfig();

    const displayModels = normalizeProviderModels(freeModels);

    return c.json({
      models: displayModels.map(model => ({
        id: model.id,
        name: model.name,
        provider: model.provider,
        context_length: model.context_length || 0,
        is_recommended: false,
        verified: verificationStatus.get(model.id)?.pending ? undefined : verificationStatus.get(model.id)?.verified,
        verify_reason: verificationStatus.get(model.id)?.pending
          ? '正在验证模型'
          : verifyReasonToMessage(verificationStatus.get(model.id)?.reason),
        last_checked_at: verificationStatus.get(model.id)?.lastCheckedAt
      })),
      current: config.default_model,
      recommended: displayModels[0]?.id || null,
      total_available: displayModels.length,
      validating: verifyingInBackground
    });
  } catch (err: any) {
    console.error('Error fetching models:', err);
    return c.json({
      error: err.message,
      details: err.toString(),
      stack: err.stack
    }, 500);
  }
});

// 3. 切换默认模型
app.put('/admin/model', async (c) => {
  try {
    const { model } = await c.req.json();
    if (!model) {
      return c.json({ error: 'Model is required' }, 400);
    }
    
    const newConfig = await setConfig({ default_model: model });
    console.log(`[${new Date().toISOString()}] Model switched to: ${model}`);
    return c.json({ model: newConfig.default_model });
  } catch (err: any) {
    return c.json({ error: err.message }, 500);
  }
});

// 4. 验证并保存 API Key
app.post('/api/validate-key', async (c) => {
  try {
    const { apiKey } = await c.req.json();
    
    if (!apiKey || typeof apiKey !== 'string' || apiKey.trim().length === 0) {
      return c.json({ success: false, error: 'API key is required' }, 400);
    }
    
    const trimmedKey = apiKey.trim();
    
    if (!trimmedKey.startsWith('sk-')) {
      return c.json({ success: false, error: 'Invalid API key format' }, 400);
    }
    
    try {
      const response = await fetchWithTimeout(
        `${ENV.OPENROUTER_BASE_URL}/models`,
        {
          headers: {
            'Authorization': `Bearer ${trimmedKey}`,
            'HTTP-Referer': 'http://localhost:8765',
            'X-Title': 'OpenRouter Free Proxy'
          }
        },
        10000
      );
      
      if (response.status === 401) {
        return c.json({ success: false, error: 'Invalid API key' }, 401);
      }
      
      if (!response.ok) {
        return c.json({ success: false, error: 'Network error, please try again later' }, 500);
      }
      
      await saveApiKey(trimmedKey);
      
      return c.json({ success: true, message: 'API key validated and saved successfully' });
    } catch (err: any) {
      if (err.name === 'AbortError') {
        return c.json({ success: false, error: 'Network error, please try again later' }, 500);
      }
      return c.json({ success: false, error: 'Network error, please try again later' }, 500);
    }
  } catch (err: any) {
    return c.json({ success: false, error: 'Server error' }, 500);
  }
});

// 5. 获取 API Key 状态
app.get('/api/validate-key', async (c) => {
  const status = await getApiKeyStatus();
  return c.json(status);
});

// 5.1 获取所有 Provider Key 状态
app.get('/api/provider-keys', async (c) => {
  const status = await getAllProviderKeysStatus();
  return c.json(status);
});

// 5.2 保存 Provider Key
app.post('/api/provider-keys', async (c) => {
  try {
    const { provider, apiKey } = await c.req.json();

    if (!provider || !apiKey) {
      return c.json({ success: false, error: 'Provider and API key are required' }, 400);
    }

    if (!Object.prototype.hasOwnProperty.call(PROVIDER_CONFIGS, provider)) {
      return c.json({ success: false, error: 'Unknown provider' }, 400);
    }

    const config = PROVIDER_CONFIGS[provider];

      try {
        const result = await validateProviderKeyWithKey(provider, String(apiKey), config.baseURL);
        if (!result.ok) {
          const status = result.reason === 'auth_failed'
            ? 401
            : result.reason === 'network_error'
              ? 500
              : 400;
          return c.json({
            success: false,
            error: verifyReasonToMessage(result.reason) || 'Provider validation failed'
          }, status as 400 | 401 | 500);
        }

        await saveProviderKey(provider, apiKey);

      const { maskApiKey } = await import('./config');
      return c.json({ success: true, masked: maskApiKey(apiKey) });
    } catch (err: any) {
      if (err.name === 'AbortError') {
        return c.json({ success: false, error: 'Connection timeout, please check your network' }, 500);
      }
      return c.json({ success: false, error: `Connection failed: ${err.message}` }, 500);
    }
  } catch (err: any) {
    return c.json({ success: false, error: 'Server error' }, 500);
  }
});

// 5.3 添加自定义 Provider
app.post('/api/custom-providers', async (c) => {
  try {
    const { name, baseURL, apiKey } = await c.req.json();

    if (!name || !baseURL || !apiKey) {
      return c.json({ success: false, error: 'Name, baseURL and apiKey are required' }, 400);
    }

    try {
      const response = await fetchWithTimeout(`${baseURL}/models`, {
        headers: { 'Authorization': `Bearer ${apiKey}` }
      });

      if (!response.ok) {
        return c.json({ success: false, error: 'Failed to connect to provider' }, 400);
      }

      await saveCustomProvider({ name, baseURL, apiKey });

      return c.json({ success: true, name });
    } catch (err) {
      return c.json({ success: false, error: 'Network error' }, 500);
    }
  } catch (err: any) {
    return c.json({ success: false, error: 'Server error' }, 500);
  }
});

// 5.4 添加自定义模型
app.post('/api/custom-models', async (c) => {
  try {
    const { provider, modelId, priority, enabled } = await c.req.json();

    if (!provider || !modelId) {
      return c.json({ success: false, error: 'Provider and modelId are required' }, 400);
    }

    const key = getProviderKey(provider);
    const providerConfig = PROVIDERS.find(p => p.name === provider);

    if (!key || !providerConfig) {
      return c.json({ success: false, error: 'Provider not configured' }, 400);
    }

    try {
      const response = await fetchWithTimeout(`${providerConfig.baseURL}/chat/completions`, {
        method: 'POST',
        headers: buildProviderHeaders(provider, key),
        body: JSON.stringify({
          model: normalizeVerificationModelId(provider, modelId),
          messages: [{ role: 'user', content: 'test' }],
          max_tokens: 1
        })
      });

      if (!response.ok) {
        return c.json({ success: false, error: 'Model not available' }, 400);
      }

      await saveCustomModel({
        provider,
        modelId,
        addedAt: Date.now(),
        priority: Number.isFinite(priority) ? Number(priority) : 100,
        enabled: enabled !== false,
        lastVerifiedAt: Date.now()
      });

      return c.json({ success: true, model: modelId });
    } catch (err) {
      return c.json({ success: false, error: 'Network error' }, 500);
    }
  } catch (err: any) {
    return c.json({ success: false, error: 'Server error' }, 500);
  }
});

// 5.5 验证手动模型
app.post('/api/custom-models/verify', async (c) => {
  try {
    const { provider, modelId } = await c.req.json();
    if (!provider || !modelId) {
      return c.json({ success: false, error: 'Provider and modelId are required' }, 400);
    }

    const parsedProvider = String(provider);
    const parsedModel = String(modelId);
    const availability = await verifyModelAvailability(parsedProvider, parsedModel);

    if (availability.verified) {
      return c.json({ success: true, verified: true, last_checked_at: availability.lastCheckedAt });
    }

    return c.json({
      success: false,
      verified: false,
      reason: availability.reason,
      message: verifyReasonToMessage(availability.reason)
    }, 400);
  } catch (err: any) {
    return c.json({ success: false, error: err.message || 'Server error' }, 500);
  }
});

// 5.6 获取手动模型
app.get('/api/custom-models', async (c) => {
  const customModels = await getCustomModels();
  return c.json({ models: customModels });
});

// 5.7 删除手动模型
app.delete('/api/custom-models/:provider/:modelId', async (c) => {
  const provider = c.req.param('provider');
  const modelId = decodeURIComponent(c.req.param('modelId'));
  const deleted = await deleteCustomModel(provider, modelId);
  if (!deleted) {
    return c.json({ success: false, error: 'Model not found' }, 404);
  }
  return c.json({ success: true });
});

// 5.8 健康检查
app.get('/api/health-check', async (c) => {
  const keyStatus = await getAllProviderKeysStatus();
  const providers = PROVIDERS.map(provider => provider.name);

  const providerHealth = await Promise.all(providers.map(async (provider) => {
    const result = await validateProviderKey(provider);
    return {
      provider,
      configured: keyStatus[provider]?.configured || false,
      ok: result.ok,
      reason: result.reason,
      message: verifyReasonToMessage(result.reason)
    };
  }));

  const hasAnyValidProvider = providerHealth.some(p => p.ok);
  const openclaw = await detectOpenClawConfig();

  return c.json({
    success: hasAnyValidProvider,
    provider_health: providerHealth,
    openclaw,
    hint: hasAnyValidProvider
      ? '环境可用，建议在客户端执行 /model free_proxy/auto'
      : '请先配置至少一个可用 provider key'
  });
});

// 6. 检测 OpenClaw 配置
app.get('/api/detect-openclaw', async (c) => {
  const status = await detectOpenClawConfig();
  return c.json(status);
});

// 7. 一键配置到 OpenClaw
app.post('/api/configure-openclaw', async (c) => {
  const providerStatus = await getAllProviderKeysStatus();
  const hasAnyConfigured = Object.values(providerStatus).some(s => s.configured);
  
  if (!hasAnyConfigured) {
    return c.json({ success: false, error: 'Please configure at least one provider API key first' }, 400);
  }
  
  const result = await mergeConfig();
  
  if (!result.success) {
    return c.json(result, 400);
  }
  
  return c.json({ success: true, backup: result.backup, message: 'Configuration successful' });
});

// 8. 获取备份列表
app.get('/api/backups', async (c) => {
  const backups = await listBackups();
  return c.json({ backups });
});

// 9. 恢复配置
app.post('/api/restore-backup', async (c) => {
  const { backup } = await c.req.json();
  
  if (!backup || typeof backup !== 'string') {
    return c.json({ success: false, error: 'Backup filename is required' }, 400);
  }
  
  const result = await restoreBackup(backup);
  
  if (!result.success) {
    return c.json(result, 400);
  }
  
  return c.json({ success: true, message: 'Restore successful' });
});

// 启动服务
if (process.env.NODE_ENV !== 'test') {
  console.log(`🚀 OpenRouter Free Proxy starting on http://localhost:${ENV.PORT}`);
  serve({
    fetch: app.fetch,
    port: ENV.PORT
  });
}
