import { describe, test, expect } from '@jest/globals';
import { app } from '../src/server';

describe('API Routes', () => {
  test('GET /api/provider-keys should return provider key status object', async () => {
    const res = await app.request('/api/provider-keys', { method: 'GET' });
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json).toHaveProperty('openrouter');
    expect(json).toHaveProperty('groq');
    expect(json).toHaveProperty('opencode');
  });

  test('PUT /admin/model should set selected model', async () => {
    const res = await app.request('/admin/model', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: 'openrouter/auto:free' })
    });
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.model).toBe('openrouter/auto:free');
  });

  test('POST /api/custom-models/verify should validate input', async () => {
    const res = await app.request('/api/custom-models/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: '', modelId: '' })
    });

    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.success).toBe(false);
  });

  test('GET /api/custom-models should return list shape', async () => {
    const res = await app.request('/api/custom-models', { method: 'GET' });
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(Array.isArray(json.models)).toBe(true);
  });

  test('GET /api/health-check should return health payload', async () => {
    const res = await app.request('/api/health-check', { method: 'GET' });
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json).toHaveProperty('provider_health');
    expect(json).toHaveProperty('hint');
  });
});
