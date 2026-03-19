import { describe, test, expect, beforeEach, afterEach } from '@jest/globals';
import { executeWithFallback, getFallbackChain } from '../src/fallback';
import { CandidatePool } from '../src/candidate-pool';
import { resetRateLimitState } from '../src/rate-limit';
import { existsSync, unlinkSync } from 'node:fs';

const RATE_LIMIT_FILE = 'rate-limit-state.fallback-candidate-test.json';

describe('Fallback - Candidate Pool Integration', () => {
  let candidatePool: CandidatePool;

  beforeEach(async () => {
    process.env.RATE_LIMIT_FILE = RATE_LIMIT_FILE;
    resetRateLimitState();
    if (existsSync(RATE_LIMIT_FILE)) {
      unlinkSync(RATE_LIMIT_FILE);
    }
    
    candidatePool = new CandidatePool();
    
    // 添加测试模型到候选池
    candidatePool.addCandidate({ id: 'model-1', name: 'Model 1' });
    candidatePool.addCandidate({ id: 'model-2', name: 'Model 2' });
    candidatePool.addCandidate({ id: 'model-3', name: 'Model 3' });
    candidatePool.addCandidate({ id: 'model-4', name: 'Model 4' });
    candidatePool.addCandidate({ id: 'model-5', name: 'Model 5' });
  });

  afterEach(() => {
    if (existsSync(RATE_LIMIT_FILE)) {
      unlinkSync(RATE_LIMIT_FILE);
    }
    delete process.env.RATE_LIMIT_FILE;
    candidatePool.clear();
  });

  describe('getFallbackChain', () => {
    test('should include all candidate pool models', async () => {
      const chain = await getFallbackChain('preferred-model');
      
      // 验证候选池的所有模型都在降级链中
      const candidates = candidatePool.getCandidates();
      for (const candidate of candidates) {
        expect(chain).toContain(candidate.id);
      }
    });

    test('should not limit to 3 models', async () => {
      const chain = await getFallbackChain(undefined);
      
      // 降级链应该包含所有候选模型，不仅仅是前 3 个
      const candidates = candidatePool.getCandidates();
      expect(chain.length).toBeGreaterThan(3);
      expect(chain.length).toBeGreaterThanOrEqual(candidates.length);
    });

    test('should include openrouter/free as fallback', async () => {
      const chain = await getFallbackChain('preferred-model');
      
      expect(chain[chain.length - 1]).toBe('openrouter/free');
    });

    test('should exclude failed models from chain', async () => {
      // 标记 model-2 和 model-3 为失败
      candidatePool.markModelFailed('model-2');
      candidatePool.markModelFailed('model-3');
      
      const chain = await getFallbackChain('preferred-model');
      
      expect(chain).not.toContain('model-2');
      expect(chain).not.toContain('model-3');
      expect(chain).toContain('model-1');
      expect(chain).toContain('model-4');
      expect(chain).toContain('model-5');
    });
  });

  describe('executeWithFallback', () => {
    test('should try all candidate models before giving up', async () => {
      const failingModels = ['model-1', 'model-2', 'model-3', 'model-4'];
      let callCount = 0;
      const attemptedModels: string[] = [];
      
      const mockExecute = async (model: string) => {
        callCount++;
        attemptedModels.push(model);
        
        // 前 4 个模型失败，第 5 个成功
        if (failingModels.includes(model)) {
          return { success: false, error: { status: 429 } };
        }
        return { success: true, response: { data: 'success' } };
      };

      const result = await executeWithFallback('preferred-model', mockExecute);

      // 验证尝试了多个模型
      expect(callCount).toBeGreaterThan(3);
      
      // 验证最后一个成功的模型
      expect(result.fallbackInfo.model).toBe('model-5');
    });

    test('should use openrouter/free as final fallback', async () => {
      let callCount = 0;
      const attemptedModels: string[] = [];
      
      const mockExecute = async (model: string) => {
        callCount++;
        attemptedModels.push(model);
        
        // 所有候选模型都失败
        if (model !== 'openrouter/free') {
          return { success: false, error: { status: 429 } };
        }
        return { success: true, response: { data: 'fallback-success' } };
      };

      const result = await executeWithFallback('preferred-model', mockExecute);

      // 验证尝试了 openrouter/free
      expect(attemptedModels).toContain('openrouter/free');
      expect(result.fallbackInfo.model).toBe('openrouter/free');
    });

    test('should throw error when all models including openrouter/free fail', async () => {
      const mockExecute = async (model: string) => ({
        success: false,
        error: { status: 429 }
      });

      await expect(executeWithFallback('preferred-model', mockExecute))
        .rejects.toThrow('All models failed');
    });

    test('should record failed models in candidate pool', async () => {
      let callCount = 0;
      
      const mockExecute = async (model: string) => {
        callCount++;
        
        // 前 3 个模型失败
        if (callCount <= 3) {
          // 标记失败
          candidatePool.markModelFailed(model);
          return { success: false, error: { status: 429 } };
        }
        return { success: true, response: { data: 'success' } };
      };

      await executeWithFallback('preferred-model', mockExecute);

      // 验证失败的模型被记录
      const candidates = candidatePool.getCandidates();
      expect(candidates.length).toBeLessThan(5); // 应该少于初始的 5 个模型
    });

    test('should provide error message without technical details', async () => {
      const mockExecute = async (model: string) => ({
        success: false,
        error: { status: 429 }
      });

      try {
        await executeWithFallback('preferred-model', mockExecute);
        expect(true).toBe(false); // Should not reach here
      } catch (error: any) {
        // 错误消息应该对小白用户友好，不包含技术细节
        expect(error.message).toContain('无可用模型');
        expect(error.message).not.toContain('rate limit');
        expect(error.message).not.toContain('429');
        expect(error.message).not.toContain('attempted_models');
      }
    });
  });
});