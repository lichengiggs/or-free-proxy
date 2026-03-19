import { describe, test, expect, beforeEach, afterEach } from '@jest/globals';
import { getModels } from '../src/models';
import { CandidatePool } from '../src/candidate-pool';

describe('Models - Candidate Pool Integration', () => {
  let candidatePool: CandidatePool;

  beforeEach(() => {
    candidatePool = new CandidatePool();
  });

  afterEach(() => {
    candidatePool.clear();
  });

  describe('GET /models', () => {
    test('should return only validated models from candidate pool', async () => {
      // 刷新候选池
      await candidatePool.refresh();
      
      const models = await getModels();
      
      expect(Array.isArray(models)).toBe(true);
      expect(models.length).toBeGreaterThan(0);
      
      // 验证所有返回的模型都在候选池中
      const candidates = candidatePool.getCandidates();
      for (const model of models) {
        const inPool = candidates.some(c => c.id === model.id);
        expect(inPool).toBe(true);
      }
    });

    test('should not return failed models', async () => {
      await candidatePool.refresh();
      
      // 标记某个模型为失败
      const models = await getModels();
      if (models.length > 0) {
        const firstModel = models[0];
        candidatePool.markModelFailed(firstModel.id);
        
        // 重新获取模型列表
        const updatedModels = await getModels();
        const hasFailedModel = updatedModels.some((m: any) => m.id === firstModel.id);
        expect(hasFailedModel).toBe(false);
      }
    });

    test('should include description field', async () => {
      await candidatePool.refresh();
      
      const models = await getModels();
      
      expect(Array.isArray(models)).toBe(true);
      for (const model of models) {
        expect(model).toHaveProperty('id');
        expect(model).toHaveProperty('name');
        expect(model).toHaveProperty('description');
      }
    });

    test('should include auto model in candidate pool', async () => {
      await candidatePool.refresh();
      
      const models = await getModels();
      
      const autoModel = models.find((m: any) => m.id === 'auto');
      expect(autoModel).toBeDefined();
      expect(autoModel.description).toContain('智能降级');
    });
  });

  describe('Model Validation', () => {
    test('should validate model availability', async () => {
      const result = await candidatePool.validateModel('deepseek/deepseek-chat');
      expect(typeof result).toBe('boolean');
    });

    test('should reject rate-limited models', async () => {
      candidatePool.markModelFailed('rate-limited/model');
      
      const isValid = await candidatePool.validateModel('rate-limited/model');
      expect(isValid).toBe(false);
    });

    test('should handle network errors gracefully', async () => {
      const isValid = await candidatePool.validateModel('network-error/model');
      expect(isValid).toBe(false);
    });
  });
});