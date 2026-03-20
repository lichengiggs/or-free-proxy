import { saveCustomProvider, saveCustomModel, CustomProvider, CustomModel } from '../src/config';

describe('Custom Provider and Model Management', () => {
  describe('saveCustomProvider', () => {
    test('should save custom provider to config', async () => {
      const customProvider: CustomProvider = {
        name: 'DeepSeek',
        baseURL: 'https://api.deepseek.com',
        apiKey: 'sk-deepseek-test'
      };
      
      await expect(saveCustomProvider(customProvider)).resolves.not.toThrow();
    });

    test('should persist custom provider across config reads', async () => {
      const customProvider: CustomProvider = {
        name: 'TestProvider',
        baseURL: 'https://api.test.com',
        apiKey: 'test-api-key'
      };
      
      await saveCustomProvider(customProvider);
      
      // Verify it was saved
      const config = await import('../src/config').then(m => m.getConfig());
      expect(config.customProviders).toBeDefined();
      expect(config.customProviders).toEqual(expect.arrayContaining([
        expect.objectContaining(customProvider)
      ]));
    });
  });

  describe('saveCustomModel', () => {
    test('should save custom model to config', async () => {
      const customModel: CustomModel = {
        provider: 'openrouter',
        modelId: 'mimo-v2-pro',
        addedAt: Date.now()
      };
      
      await expect(saveCustomModel(customModel)).resolves.not.toThrow();
    });

    test('should persist custom model across config reads', async () => {
      const customModel: CustomModel = {
        provider: 'groq',
        modelId: 'test-model',
        addedAt: Date.now()
      };
      
      await saveCustomModel(customModel);
      
      const config = await import('../src/config').then(m => m.getConfig());
      expect(config.customModels).toBeDefined();
      expect(config.customModels).toEqual(expect.arrayContaining([
        expect.objectContaining(customModel)
      ]));
    });

    test('should allow multiple custom models for same provider', async () => {
      const model1: CustomModel = {
        provider: 'openrouter',
        modelId: 'model-1',
        addedAt: Date.now()
      };
      
      const model2: CustomModel = {
        provider: 'openrouter',
        modelId: 'model-2',
        addedAt: Date.now()
      };
      
      await saveCustomModel(model1);
      await saveCustomModel(model2);
      
      const config = await import('../src/config').then(m => m.getConfig());
      const models = config.customModels?.filter(m => m.provider === 'openrouter');
      expect(models?.length).toBeGreaterThanOrEqual(2);
    });
  });
});
