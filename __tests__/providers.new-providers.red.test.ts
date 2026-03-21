import { describe, expect, test } from '@jest/globals';
import { PROVIDERS } from '../src/providers/registry';
import { getAllProviderKeysStatus } from '../src/config';

describe('new provider registration (red phase)', () => {
  test('should include Gemini provider', () => {
    expect(PROVIDERS.find(p => p.name === 'gemini')).toBeDefined();
  });

  test('should include GitHub Models provider', () => {
    expect(PROVIDERS.find(p => p.name === 'github')).toBeDefined();
  });

  test('should include Mistral provider', () => {
    expect(PROVIDERS.find(p => p.name === 'mistral')).toBeDefined();
  });

  test('should include Cerebras provider', () => {
    expect(PROVIDERS.find(p => p.name === 'cerebras')).toBeDefined();
  });

  test('should include SambaNova provider', () => {
    expect(PROVIDERS.find(p => p.name === 'sambanova')).toBeDefined();
  });

  test('should expose all provider keys in status', async () => {
    const status = await getAllProviderKeysStatus();

    expect(status).toHaveProperty('openrouter');
    expect(status).toHaveProperty('groq');
    expect(status).toHaveProperty('opencode');
    expect(status).toHaveProperty('gemini');
    expect(status).toHaveProperty('github');
    expect(status).toHaveProperty('mistral');
    expect(status).toHaveProperty('cerebras');
    expect(status).toHaveProperty('sambanova');
  });

  test('should register at least 8 providers', () => {
    expect(PROVIDERS).toHaveLength(8);
  });
});
