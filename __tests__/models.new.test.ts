import { describe, test, expect } from '@jest/globals';
import { isEffectivelyFreeModel } from '../src/models';

describe('models module new behaviors', () => {
  test('should treat opencode -free model as free', () => {
    const result = isEffectivelyFreeModel({
      id: 'opencode/model-free',
      provider: 'opencode',
      pricing: { prompt: '1', completion: '1' }
    });
    expect(result).toBe(true);
  });

  test('should treat non-opencode zero pricing model as free', () => {
    const result = isEffectivelyFreeModel({
      id: 'openrouter/some-model',
      provider: 'openrouter',
      pricing: { prompt: '0', completion: '0' }
    });
    expect(result).toBe(true);
  });

  test('should treat non-zero pricing model as not free', () => {
    const result = isEffectivelyFreeModel({
      id: 'openrouter/paid-model',
      provider: 'openrouter',
      pricing: { prompt: '0.1', completion: '0' }
    });
    expect(result).toBe(false);
  });
});
