import { describe, test, expect, beforeEach, afterEach } from '@jest/globals';
import { getFallbackChain, executeWithFallback } from '../src/fallback';
import { resetRateLimitState, isModelRateLimited, markModelRateLimited } from '../src/rate-limit';
import { existsSync, unlinkSync } from 'node:fs';

const RATE_LIMIT_FILE = 'rate-limit-state.fallback-test.json';

describe('fallback module', () => {
  beforeEach(async () => {
    process.env.RATE_LIMIT_FILE = RATE_LIMIT_FILE;
    resetRateLimitState();
    if (existsSync(RATE_LIMIT_FILE)) {
      unlinkSync(RATE_LIMIT_FILE);
    }
  });

  afterEach(() => {
    if (existsSync(RATE_LIMIT_FILE)) {
      unlinkSync(RATE_LIMIT_FILE);
    }
    delete process.env.RATE_LIMIT_FILE;
  });

  describe('getFallbackChain', () => {
    test('should include preferred model as first option', async () => {
      const chain = await getFallbackChain('my-preferred-model');
      expect(chain[0]).toBe('my-preferred-model');
    });

    test('should include openrouter/free as last option', async () => {
      const chain = await getFallbackChain('preferred-model');
      expect(chain[chain.length - 1]).toBe('openrouter/free');
    });

    test('should include top 3 ranked models when preferred is not set', async () => {
      const chain = await getFallbackChain(undefined);
      expect(chain.length).toBeGreaterThan(1);
      expect(chain[chain.length - 1]).toBe('openrouter/free');
    });

    test('should not duplicate models', async () => {
      const chain = await getFallbackChain('model-1');
      const uniqueChain = [...new Set(chain)];
      expect(chain.length).toBe(uniqueChain.length);
    });
  });

  describe('executeWithFallback', () => {
    test('should use preferred model when it works', async () => {
      const mockExecute = async (model: string) => ({
        success: true,
        response: { data: 'success' }
      });

      const result = await executeWithFallback('preferred-model', mockExecute);

      expect(result.fallbackInfo.is_fallback).toBe(false);
      expect(result.fallbackInfo.model).toBe('preferred-model');
    });

    test('should fallback when preferred model fails', async () => {
      let callCount = 0;
      const mockExecute = async (model: string) => {
        callCount++;
        if (callCount === 1) {
          return { success: false, error: { status: 429 } };
        }
        return { success: true, response: { data: 'fallback' } };
      };

      const result = await executeWithFallback('failing-model', mockExecute);

      expect(result.fallbackInfo.is_fallback).toBe(true);
      expect(callCount).toBe(2);
    });

    test('should skip rate limited models', async () => {
      await markModelRateLimited('preferred-model', 'rate_limit');
      
      let calledModel: string | null = null;
      const mockExecute = async (model: string) => {
        calledModel = model;
        return { success: true, response: { data: 'success' } };
      };

      await executeWithFallback('preferred-model', mockExecute);

      expect(calledModel).not.toBe('preferred-model');
      expect(isModelRateLimited('preferred-model')).toBe(true);
    });

    test('should mark model as rate limited on 429 error', async () => {
      let callCount = 0;
      const mockExecute = async (model: string) => {
        callCount++;
        if (callCount === 1) {
          return { success: false, error: { status: 429, retry_after: 3600 } };
        }
        return { success: true, response: { data: 'success' } };
      };

      await executeWithFallback('rate-limited-model', mockExecute);

      expect(isModelRateLimited('rate-limited-model')).toBe(true);
    });

    test('should mark model as unavailable on 503 error', async () => {
      let callCount = 0;
      const mockExecute = async (model: string) => {
        callCount++;
        if (callCount === 1) {
          return { success: false, error: { status: 503 } };
        }
        return { success: true, response: { data: 'success' } };
      };

      await executeWithFallback('unavailable-model', mockExecute);

      expect(isModelRateLimited('unavailable-model')).toBe(true);
    });

    test('should include attempted models in result', async () => {
      let callCount = 0;
      const mockExecute = async (model: string) => {
        callCount++;
        if (callCount <= 2) {
          return { success: false, error: { status: 429 } };
        }
        return { success: true, response: { data: 'success' } };
      };

      const result = await executeWithFallback('first-model', mockExecute);

      expect(result.fallbackInfo.attempted_models.length).toBeGreaterThan(0);
    });

    test('should throw error when all models fail', async () => {
      const mockExecute = async (model: string) => ({
        success: false,
        error: { status: 429 }
      });

      await expect(executeWithFallback('model', mockExecute)).rejects.toThrow('All models failed');
    });

    test('should provide fallback reason when using fallback', async () => {
      let callCount = 0;
      const mockExecute = async (model: string) => {
        callCount++;
        if (callCount === 1) {
          return { success: false, error: { status: 429 } };
        }
        return { success: true, response: { data: 'success' } };
      };

      const result = await executeWithFallback('preferred-model', mockExecute);

      expect(result.fallbackInfo.fallback_reason).toContain('preferred-model unavailable');
      expect(result.fallbackInfo.fallback_reason).toContain('fallback to');
    });
  });
});
