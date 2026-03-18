import { serve } from '@hono/node-server';
import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { serveStatic } from '@hono/node-server/serve-static';
import { stream } from 'hono/streaming';
import { getConfig, setConfig, ENV, fetchWithTimeout } from './config';
import { fetchModels, filterFreeModels, rankModels } from './models';
import { executeWithFallback } from './fallback';

const app = new Hono();

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

// 2. 获取模型列表
app.get('/admin/models', async (c) => {
  try {
    const forceRefresh = c.req.query('refresh') === 'true';
    const models = await fetchModels(forceRefresh);
    const freeModels = filterFreeModels(models);
    const rankedModels = rankModels(freeModels);
    const config = await getConfig();

    return c.json({
      models: rankedModels.map(({ model, score, reasons }) => ({
        id: model.id,
        name: model.name,
        context_length: model.context_length,
        score,
        reasons,
        is_recommended: score >= 80
      })),
      current: config.default_model,
      recommended: rankedModels[0]?.model.id
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

// 启动服务
if (process.env.NODE_ENV !== 'test') {
  console.log(`🚀 OpenRouter Free Proxy starting on http://localhost:${ENV.PORT}`);
  serve({
    fetch: app.fetch,
    port: ENV.PORT
  });
}
