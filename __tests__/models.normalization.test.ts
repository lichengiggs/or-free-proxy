import { describe, test, expect } from '@jest/globals';
import { normalizeProviderModelId, resolveProviderModelName } from '../src/models';

describe('provider model normalization helpers', () => {
  test('normalizeProviderModelId should normalize gemini prefix', () => {
    expect(normalizeProviderModelId('gemini', 'models/gemini-3.1-flash-lite-preview')).toBe('gemini-3.1-flash-lite-preview');
  });

  test('normalizeProviderModelId should normalize github model path', () => {
    const id = 'https://host/models/gpt-4o-mini/versions/1';
    expect(normalizeProviderModelId('github', id)).toBe('gpt-4o-mini');
  });

  test('normalizeProviderModelId should normalize opencode models/ prefix', () => {
    expect(normalizeProviderModelId('opencode', 'models/mimo-v2-pro-free')).toBe('mimo-v2-pro-free');
  });

  test('resolveProviderModelName should prefer explicit name', () => {
    const name = resolveProviderModelName('github', {
      id: 'https://host/models/gpt-4o-mini/versions/1',
      name: 'Custom Name',
      friendly_name: 'Friendly Name'
    } as any);
    expect(name).toBe('Custom Name');
  });

  test('resolveProviderModelName should fallback to friendly_name then normalized id', () => {
    const withFriendly = resolveProviderModelName('github', {
      id: 'https://host/models/gpt-4o-mini/versions/1',
      friendly_name: 'Friendly Name'
    } as any);
    expect(withFriendly).toBe('Friendly Name');

    const withoutName = resolveProviderModelName('gemini', {
      id: 'models/gemini-3.1-flash-lite-preview'
    } as any);
    expect(withoutName).toBe('gemini-3.1-flash-lite-preview');
  });
});
