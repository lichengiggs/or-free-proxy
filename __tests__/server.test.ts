import { describe, test, expect } from '@jest/globals';
import { app } from '../src/server';

describe('API endpoints', () => {
  test('PUT /admin/model should accept any model', async () => {
    const res = await app.request('/admin/model', {
      method: 'PUT',
      body: JSON.stringify({ model: 'any-model-name' }),
      headers: { 'Content-Type': 'application/json' }
    });
    
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.model).toBe('any-model-name');
  });

  test('PUT /admin/model should reject missing model field', async () => {
    const res = await app.request('/admin/model', {
      method: 'PUT',
      body: JSON.stringify({}),
      headers: { 'Content-Type': 'application/json' }
    });
    
    expect(res.status).toBe(400);
  });

  test('PUT /admin/model should reject empty model', async () => {
    const res = await app.request('/admin/model', {
      method: 'PUT',
      body: JSON.stringify({ model: '' }),
      headers: { 'Content-Type': 'application/json' }
    });
    
    expect(res.status).toBe(400);
  });
});
