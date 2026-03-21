import { describe, test, expect } from '@jest/globals';
import { buildProviderHeaders, normalizeVerificationModelId } from '../src/provider-health';

describe('provider-health new helpers', () => {
  test('buildProviderHeaders should include OpenRouter required headers', () => {
    const headers = buildProviderHeaders('openrouter', 'sk-test');
    expect(headers.Authorization).toBe('Bearer sk-test');
    expect(headers['Content-Type']).toBe('application/json');
    expect(headers['HTTP-Referer']).toBe('http://localhost:8765');
    expect(headers['X-Title']).toBe('OpenRouter Free Proxy');
  });

  test('buildProviderHeaders should not include OpenRouter extras for others', () => {
    const headers = buildProviderHeaders('groq', 'gsk-test');
    expect(headers.Authorization).toBe('Bearer gsk-test');
    expect(headers['Content-Type']).toBe('application/json');
    expect(headers['HTTP-Referer']).toBeUndefined();
    expect(headers['X-Title']).toBeUndefined();
  });

  test('buildProviderHeaders should use x-goog-api-key for gemini', () => {
    const headers = buildProviderHeaders('gemini', 'AIza-test');
    expect(headers.Authorization).toBeUndefined();
    expect(headers['x-goog-api-key']).toBe('AIza-test');
    expect(headers['Content-Type']).toBe('application/json');
  });

  test('normalizeVerificationModelId should add models/ for gemini', () => {
    expect(normalizeVerificationModelId('gemini', 'gemini-3.1-flash-lite-preview')).toBe('models/gemini-3.1-flash-lite-preview');
  });

  test('normalizeVerificationModelId should keep existing models/ prefix', () => {
    expect(normalizeVerificationModelId('gemini', 'models/gemini-3.1-flash-lite-preview')).toBe('models/gemini-3.1-flash-lite-preview');
  });

  test('normalizeVerificationModelId should keep other providers unchanged', () => {
    expect(normalizeVerificationModelId('openrouter', 'stepfun/step-3.5-flash:free')).toBe('stepfun/step-3.5-flash:free');
  });
});
