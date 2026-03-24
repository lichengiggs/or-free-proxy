import { fetchAllModels, fetchProviderModels, __MODEL_TEST_ONLY__ } from '../src/models';
import { PROVIDERS } from '../src/providers/registry';

describe('Multi-Provider Model Fetching', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    __MODEL_TEST_ONLY__.clearProviderModelCache();
    process.env.NODE_ENV = 'test';
    global.fetch = (async (input: RequestInfo | URL) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.includes('openrouter.ai')) {
        return new Response(JSON.stringify({ data: [{ id: 'openai/gpt-oss-20b:free', name: 'GPT OSS 20B' }] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      if (url.includes('api.groq.com')) {
        throw new Error('network down');
      }
      if (url.includes('generativelanguage.googleapis.com')) {
        return new Response(JSON.stringify({ models: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      if (url.includes('models.github.ai')) {
        return new Response(JSON.stringify({ items: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      return new Response(JSON.stringify({ data: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      });
    }) as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  describe('fetchAllModels', () => {
    test('should return empty array when no providers configured', async () => {
      delete process.env.OPENROUTER_API_KEY;
      delete process.env.GROQ_API_KEY;
      delete process.env.OPENCODE_API_KEY;
      delete process.env.GEMINI_API_KEY;
      delete process.env.GITHUB_MODELS_API_KEY;
      delete process.env.MISTRAL_API_KEY;
      delete process.env.CEREBRAS_API_KEY;
      delete process.env.SAMBANOVA_API_KEY;
      
      const models = await fetchAllModels();
      expect(models).toEqual([]);
    });

    test('should fetch models from configured provider', async () => {
      process.env.OPENROUTER_API_KEY = 'test-key';
      
      const models = await fetchAllModels();
      expect(Array.isArray(models)).toBe(true);
      
      delete process.env.OPENROUTER_API_KEY;
    });

    test('should prefix model IDs with provider name', async () => {
      process.env.OPENROUTER_API_KEY = 'test-key';
      
      const models = await fetchAllModels();
      if (models.length > 0) {
        expect(models[0].id).toMatch(/^(openrouter|groq|opencode)\//);
        expect(models[0].provider).toBeDefined();
      }
      
      delete process.env.OPENROUTER_API_KEY;
    });

    test('should handle network errors gracefully', async () => {
      process.env.GROQ_API_KEY = 'invalid-key';
      
      const models = await fetchAllModels();
      expect(Array.isArray(models)).toBe(true);
      
      delete process.env.GROQ_API_KEY;
    });

    test('should keep two gemini fallback models when models endpoint is unavailable', async () => {
      const originalFetch = global.fetch;
      process.env.GEMINI_API_KEY = 'test-gemini-key';

      global.fetch = (async () => {
        throw new Error('network down');
      }) as typeof fetch;

      const gemini = PROVIDERS.find(p => p.name === 'gemini');
      const models = await fetchProviderModels(gemini!, 'test-gemini-key');

      expect(models.map(model => model.id)).toEqual([
        'gemini/gemini-3.1-flash-lite-preview',
        'gemini/gemma-3-27b-it'
      ]);

      global.fetch = originalFetch;
      delete process.env.GEMINI_API_KEY;
    });

    test('should parse Gemini API models payload shape', async () => {
      const originalFetch = global.fetch;
      const gemini = PROVIDERS.find(p => p.name === 'gemini');

      global.fetch = (async () => new Response(JSON.stringify({
        models: [
          { name: 'models/gemini-3.1-flash-lite-preview', displayName: 'Gemini 3.1 Flash Lite Preview' },
          { name: 'models/gemma-3-27b-it', displayName: 'Gemma 3 27B' }
        ]
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      })) as typeof fetch;

      const models = await fetchProviderModels(gemini!, 'test-gemini-key');
      expect(models.map(model => model.id)).toEqual([
        'gemini/gemini-3.1-flash-lite-preview',
        'gemini/gemma-3-27b-it'
      ]);

      global.fetch = originalFetch;
    });

    test('should parse GitHub items payload shape', async () => {
      const originalFetch = global.fetch;
      const github = PROVIDERS.find(p => p.name === 'github');

      global.fetch = (async () => new Response(JSON.stringify({
        items: [
          { slug: 'gpt-4o-mini', name: 'GPT-4o Mini', model_family: 'gpt' },
          { slug: 'phi-3.5-mini', name: 'Phi 3.5 Mini', model_family: 'phi', task: 'chat-completion' }
        ]
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      })) as typeof fetch;

      const models = await fetchProviderModels(github!, 'test-github-key');
      expect(models.map(model => model.id)).toContain('github/gpt-4o-mini');

      global.fetch = originalFetch;
    });

    test('should fall back to default GitHub model when payload has no recognized chat models', async () => {
      const originalFetch = global.fetch;
      const github = PROVIDERS.find(p => p.name === 'github');

      global.fetch = (async () => new Response(JSON.stringify({ items: [{ slug: 'embedding-only' }] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      })) as typeof fetch;

      const models = await fetchProviderModels(github!, 'test-github-key');
      expect(models.map(model => model.id)).toEqual(['github/gpt-4o-mini']);

      global.fetch = originalFetch;
    });
  });
});
