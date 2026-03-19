import { serve } from '@hono/node-server';
import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { serveStatic } from '@hono/node-server/serve-static';
import { stream } from 'hono/streaming';
import { getConfig, setConfig, ENV, fetchWithTimeout, saveApiKey, getApiKeyStatus } from './config';
import { fetchModels, filterFreeModels, rankModels } from './models';
import { executeWithFallback } from './fallback';
import { detectOpenClawConfig, mergeConfig, listBackups, restoreBackup } from './openclaw-config';
import { CandidatePool } from './candidate-pool';

const app = new Hono();
const candidatePool = new CandidatePool();

export { app, getConfig, setConfig };

// CORS 配置
app.use('/*', cors({
  origin: (origin) => {
    if (origin.startsWith('http://localhost:') || origin === 'null') {
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

// 1. Chat Completions 接口
app.post('/v1/chat/completions', async (c) => {
  try {
    const body = await c.req.json();
    const headers = Object.fromEntries(c.req.raw.headers.entries());
    const config = await getConfig();

    const result = await executeWithFallback(
      config.default_model,
      async (modelToTry) => {
        body.model = modelToTry;

        const proxyHeaders: Record<string, string> = {
          'Authorization': `Bearer ${ENV.OPENROUTER_API_KEY}`,
          'HTTP-Referer': 'http://localhost:8765',
          'X-Title': 'OpenRouter Free Proxy',
          'Content-Type': 'application/json'
        };

        Object.entries(headers).forEach(([key, value]) => {
          if (!['host', 'content-length', 'authorization'].includes(key.toLowerCase())) {
            proxyHeaders[key] = value;
          }
        });

        try {
          const response = await fetchWithTimeout(
            `${ENV.OPENROUTER_BASE_URL}/chat/completions`,
            {
              method: 'POST',
              headers: proxyHeaders,
              body: JSON.stringify(body)
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
    return c.json(data, { status: response.status as any });

  } catch (err: any) {
    console.error(`[${new Date().toISOString()}] Request error:`, err.message);
    return c.json({
      error: {
        message: err.message,
        type: 'internal_error',
        code: 500
      }
    }, 500);
  }
});

// 2. 获取模型列表（只返回验证可用的）
app.get('/admin/models', async (c) => {
  try {
    const forceRefresh = c.req.query('refresh') === 'true';
    
    if (forceRefresh || candidatePool.getCandidates().length === 0) {
      await candidatePool.refresh();
    }
    
    const candidates = candidatePool.getCandidates();
    const config = await getConfig();

    return c.json({
      models: candidates.map(candidate => ({
        id: candidate.id,
        name: candidate.name,
        context_length: candidate.context_length || 0,
        is_recommended: true,
        last_validated: candidate.lastValidated
      })),
      current: config.default_model,
      recommended: candidates[0]?.id,
      total_available: candidates.length,
      last_update: candidatePool.getLastUpdateTime()
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

// 6. 检测 OpenClaw 配置
app.get('/api/detect-openclaw', async (c) => {
  const status = await detectOpenClawConfig();
  return c.json(status);
});

// 7. 一键配置到 OpenClaw
app.post('/api/configure-openclaw', async (c) => {
  const status = await getApiKeyStatus();
  
  if (!status.configured) {
    return c.json({ success: false, error: 'Please validate your API key first' }, 400);
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
