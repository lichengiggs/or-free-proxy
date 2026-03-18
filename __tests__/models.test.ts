import { describe, test, expect } from '@jest/globals';
import { filterFreeModels, rankModels, getRecommendedModel, extractParameterScore } from '../src/models';

describe('models module', () => {
  describe('filterFreeModels', () => {
    test('should only return models with :free suffix', () => {
      const models = [
        { id: 'meta-llama/llama-3.2-3b-instruct:free', name: 'Llama 3.2 3B', context_length: 4096, pricing: { prompt: '0', completion: '0' }, description: '' },
        { id: 'openai/gpt-4o', name: 'GPT-4o', context_length: 4096, pricing: { prompt: '0.03', completion: '0.06' }, description: '' },
        { id: 'anthropic/claude-3-haiku:free', name: 'Claude 3 Haiku', context_length: 4096, pricing: { prompt: '0', completion: '0' }, description: '' },
        { id: 'deepseek/deepseek-chat:free', name: 'DeepSeek Chat', context_length: 4096, pricing: { prompt: '0', completion: '0' }, description: '' },
        { id: 'google/gemini-1.5-flash', name: 'Gemini 1.5 Flash', context_length: 4096, pricing: { prompt: '0.01', completion: '0.02' }, description: '' }
      ] as any;

      const freeModels = filterFreeModels(models);
      expect(freeModels.length).toBe(3);
      expect(freeModels.map(m => m.id)).toEqual([
        'anthropic/claude-3-haiku:free',
        'deepseek/deepseek-chat:free',
        'meta-llama/llama-3.2-3b-instruct:free'
      ]);
    });

    test('should return empty array when no free models', () => {
      const models = [
        { id: 'openai/gpt-4o', name: 'GPT-4o', context_length: 4096, pricing: { prompt: '0.03', completion: '0.06' }, description: '' },
        { id: 'anthropic/claude-3.5-sonnet', name: 'Claude 3.5 Sonnet', context_length: 4096, pricing: { prompt: '0.015', completion: '0.075' }, description: '' }
      ] as any;

      const freeModels = filterFreeModels(models);
      expect(freeModels.length).toBe(0);
    });

    test('should also return models with pricing=0 even without :free suffix', () => {
      const models = [
        { id: 'meta-llama/llama-3.2-3b-instruct:free', name: 'Llama 3.2 3B', context_length: 4096, pricing: { prompt: '0', completion: '0' }, description: '' },
        { id: 'github/gpt-4o', name: 'GPT-4o via GitHub', context_length: 128000, pricing: { prompt: '0', completion: '0' }, description: '' },
        { id: 'google/gemini-pro', name: 'Gemini Pro', context_length: 32000, pricing: { prompt: '0', completion: '0' }, description: '' },
        { id: 'openai/gpt-4', name: 'GPT-4', context_length: 8192, pricing: { prompt: '0.03', completion: '0.06' }, description: '' }
      ] as any;

      const freeModels = filterFreeModels(models);
      expect(freeModels.length).toBe(3);
      expect(freeModels.map(m => m.id)).toContain('github/gpt-4o');
      expect(freeModels.map(m => m.id)).toContain('google/gemini-pro');
    });

    test('should not return models with non-zero pricing', () => {
      const models = [
        { id: 'openai/gpt-4', name: 'GPT-4', context_length: 8192, pricing: { prompt: '0.03', completion: '0.06' }, description: '' },
        { id: 'anthropic/claude-3-opus', name: 'Claude 3 Opus', context_length: 200000, pricing: { prompt: '0.015', completion: '0.075' }, description: '' },
        { id: 'meta-llama/llama-3.2-3b-instruct:free', name: 'Llama 3.2 3B', context_length: 4096, pricing: { prompt: '0', completion: '0' }, description: '' }
      ] as any;

      const freeModels = filterFreeModels(models);
      expect(freeModels.length).toBe(1);
      expect(freeModels[0].id).toBe('meta-llama/llama-3.2-3b-instruct:free');
    });
  });

  describe('extractParameterScore', () => {
    test('should extract 70B parameters and return high score', () => {
      const result = extractParameterScore('Meta-Llama-3.1-70B-Instruct');
      expect(result.score).toBe(20);
      expect(result.reason).toBe('大参数(70B)');
    });

    test('should extract 7B parameters and return low score', () => {
      const result = extractParameterScore('Llama-2-7b-chat');
      expect(result.score).toBe(5);
      expect(result.reason).toBe('轻量参数(7B)');
    });

    test('should extract 1.5B parameters', () => {
      const result = extractParameterScore('Qwen2.5-1.5B-Instruct');
      expect(result.score).toBe(2);
      expect(result.reason).toBe('小参数(1.5B)');
    });

    test('should handle lowercase b', () => {
      const result = extractParameterScore('model-13b-v1');
      expect(result.score).toBe(10);
      expect(result.reason).toBe('标准参数(13B)');
    });

    test('should handle uppercase B', () => {
      const result = extractParameterScore('Model-32B-V2');
      expect(result.score).toBe(15);
      expect(result.reason).toBe('中参数(32B)');
    });

    test('should return 0 score when no parameter found', () => {
      const result = extractParameterScore('GPT-4 Turbo');
      expect(result.score).toBe(0);
      expect(result.reason).toBeUndefined();
    });

    test('should handle 72B models', () => {
      const result = extractParameterScore('Qwen-72B-Chat');
      expect(result.score).toBe(20);
      expect(result.reason).toBe('大参数(72B)');
    });
  });

  describe('rankModels', () => {
    test('should rank models by score', () => {
      const models = [
        { id: 'provider/small-7b:free', name: 'Small 7B', context_length: 4096, pricing: { prompt: '0', completion: '0' }, description: '' },
        { id: 'meta-llama/llama-3.1-70b:free', name: 'Llama 3.1 70B', context_length: 128000, pricing: { prompt: '0', completion: '0' }, description: '' },
        { id: 'provider/medium-13b:free', name: 'Medium 13B', context_length: 8192, pricing: { prompt: '0', completion: '0' }, description: '' }
      ] as any;

      const ranked = rankModels(models);
      expect(ranked[0].model.id).toBe('meta-llama/llama-3.1-70b:free');
      expect(ranked[0].score).toBeGreaterThan(80);
      expect(ranked[0].reasons).toContain('大参数(70B)');
    });

    test('should give higher score to trusted providers', () => {
      const models = [
        { id: 'meta-llama/llama-3.2-3b:free', name: 'Llama 3.2 3B', context_length: 4096, pricing: { prompt: '0', completion: '0' }, description: '' },
        { id: 'unknown/model-3b:free', name: 'Unknown 3B', context_length: 4096, pricing: { prompt: '0', completion: '0' }, description: '' }
      ] as any;

      const ranked = rankModels(models);
      expect(ranked[0].model.id).toBe('meta-llama/llama-3.2-3b:free');
    });

    test('should score based on context length', () => {
      const models = [
        { id: 'provider/small-context:free', name: 'Small Context', context_length: 4096, pricing: { prompt: '0', completion: '0' }, description: '' },
        { id: 'provider/large-context:free', name: 'Large Context', context_length: 128000, pricing: { prompt: '0', completion: '0' }, description: '' }
      ] as any;

      const ranked = rankModels(models);
      expect(ranked[0].model.id).toBe('provider/large-context:free');
      expect(ranked[0].reasons).toContain('超长上下文(32k+)');
    });
  });

  describe('getRecommendedModel', () => {
    test('should return the highest scored model', () => {
      const models = [
        { id: 'provider/small:free', name: 'Small', context_length: 4096, pricing: { prompt: '0', completion: '0' }, description: '' },
        { id: 'meta-llama/llama-3.1-70b:free', name: 'Llama 70B', context_length: 128000, pricing: { prompt: '0', completion: '0' }, description: '' },
        { id: 'provider/medium:free', name: 'Medium', context_length: 8192, pricing: { prompt: '0', completion: '0' }, description: '' }
      ] as any;

      const recommended = getRecommendedModel(models);
      expect(recommended).not.toBeNull();
      expect(recommended?.model.id).toBe('meta-llama/llama-3.1-70b:free');
      expect(recommended?.score).toBeGreaterThan(80);
    });

    test('should return null when no models provided', () => {
      const recommended = getRecommendedModel([]);
      expect(recommended).toBeNull();
    });
  });
});
