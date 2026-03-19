import { describe, test, expect, beforeEach, afterEach } from '@jest/globals';
import { CandidatePool } from '../src/candidate-pool';
import { existsSync, unlinkSync } from 'node:fs';
import { join } from 'node:path';

describe('CandidatePool', () => {
  let candidatePool: CandidatePool;

  beforeEach(() => {
    candidatePool = new CandidatePool();
  });

  afterEach(() => {
    candidatePool.clear();
  });

  describe('validateModel', () => {
    test('should return true for valid model', async () => {
      const result = await candidatePool.validateModel('deepseek/deepseek-chat');
      expect(result).toBe(true);
    });

    test('should return false for invalid model', async () => {
      const result = await candidatePool.validateModel('invalid/model');
      expect(result).toBe(false);
    });

    test('should return false for rate-limited model', async () => {
      // 先标记模型为失败
      candidatePool.markModelFailed('rate-limited/model');
      
      const result = await candidatePool.validateModel('rate-limited/model');
      expect(result).toBe(false);
    });

    test('should handle network errors gracefully', async () => {
      // 模拟网络错误
      const result = await candidatePool.validateModel('network-error/model');
      expect(result).toBe(false);
    });
  });

  describe('refresh', () => {
    test('should refresh candidate pool from OpenRouter', async () => {
      await candidatePool.refresh();
      
      const candidates = candidatePool.getCandidates();
      expect(candidates.length).toBeGreaterThan(0);
    });

    test('should only include validated models', async () => {
      await candidatePool.refresh();
      
      const candidates = candidatePool.getCandidates();
      for (const candidate of candidates) {
        const isValid = await candidatePool.validateModel(candidate.id);
        expect(isValid).toBe(true);
      }
    });

    test('should clear previous candidates on refresh', async () => {
      candidatePool.addCandidate({ id: 'test/model', name: 'Test Model' });
      expect(candidatePool.getCandidates().length).toBe(1);
      
      await candidatePool.refresh();
      
      // 刷新后不应该包含手工添加的测试模型
      const candidates = candidatePool.getCandidates();
      const hasTestModel = candidates.some(c => c.id === 'test/model');
      expect(hasTestModel).toBe(false);
    });
  });

  describe('getCandidates', () => {
    test('should return empty array when no candidates', () => {
      const candidates = candidatePool.getCandidates();
      expect(candidates).toEqual([]);
    });

    test('should return all candidates', () => {
      candidatePool.addCandidate({ id: 'model1', name: 'Model 1' });
      candidatePool.addCandidate({ id: 'model2', name: 'Model 2' });
      
      const candidates = candidatePool.getCandidates();
      expect(candidates.length).toBe(2);
    });

    test('should not include failed models', () => {
      candidatePool.addCandidate({ id: 'model1', name: 'Model 1' });
      candidatePool.addCandidate({ id: 'model2', name: 'Model 2' });
      candidatePool.markModelFailed('model1');
      
      const candidates = candidatePool.getCandidates();
      expect(candidates.length).toBe(1);
      expect(candidates[0].id).toBe('model2');
    });
  });

  describe('markModelFailed', () => {
    test('should mark model as failed', () => {
      candidatePool.addCandidate({ id: 'test/model', name: 'Test Model' });
      candidatePool.markModelFailed('test/model');
      
      const candidates = candidatePool.getCandidates();
      expect(candidates.length).toBe(0);
    });

    test('should ignore non-existent model', () => {
      expect(() => {
        candidatePool.markModelFailed('non-existent/model');
      }).not.toThrow();
    });
  });

  describe('addCandidate', () => {
    test('should add candidate to pool', () => {
      candidatePool.addCandidate({ id: 'test/model', name: 'Test Model' });
      
      const candidates = candidatePool.getCandidates();
      expect(candidates.length).toBe(1);
      expect(candidates[0].id).toBe('test/model');
    });

    test('should not duplicate candidates', () => {
      candidatePool.addCandidate({ id: 'test/model', name: 'Test Model' });
      candidatePool.addCandidate({ id: 'test/model', name: 'Test Model' });
      
      const candidates = candidatePool.getCandidates();
      expect(candidates.length).toBe(1);
    });
  });

  describe('clear', () => {
    test('should clear all candidates', () => {
      candidatePool.addCandidate({ id: 'model1', name: 'Model 1' });
      candidatePool.addCandidate({ id: 'model2', name: 'Model 2' });
      
      candidatePool.clear();
      
      const candidates = candidatePool.getCandidates();
      expect(candidates).toEqual([]);
    });
  });

  describe('getLastUpdateTime', () => {
    test('should return null before refresh', () => {
      const lastUpdate = candidatePool.getLastUpdateTime();
      expect(lastUpdate).toBeNull();
    });

    test('should return timestamp after refresh', async () => {
      await candidatePool.refresh();
      
      const lastUpdate = candidatePool.getLastUpdateTime();
      expect(lastUpdate).not.toBeNull();
      expect(typeof lastUpdate).toBe('number');
    });
  });
});