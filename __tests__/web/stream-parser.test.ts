import { jest } from '@jest/globals';
import { readFileSync } from 'node:fs';

function extractHelpers(): string {
  const html = readFileSync('python_scripts/web/index.html', 'utf-8');
  const start = html.indexOf('function extractSseDataLine');
  const end = html.indexOf('function setDiagnostics', start);
  if (start === -1 || end === -1) {
    throw new Error('stream helpers not found');
  }
  return html.slice(start, end);
}

describe('web stream parser', () => {
  test('requestStream accepts SSE data lines without trailing space', async () => {
    const source = `${extractHelpers()} return requestStream;`;
    const factory = new Function(source);
    const requestStream = factory() as (url: string, options?: object, onChunk?: (chunk: string, fullText: string) => void) => Promise<string>;

    const chunks = [
      'data:{"choices":[{"delta":{"content":"OK"},"index":0}]}\n\n',
      'data:[DONE]\n\n',
    ];

    global.fetch = jest.fn(async () => ({
      ok: true,
      headers: { get: () => 'text/event-stream; charset=utf-8' },
      body: {
        getReader() {
          let index = 0;
          return {
            async read() {
              if (index >= chunks.length) {
                return { done: true, value: undefined };
              }
              const value = new TextEncoder().encode(chunks[index]);
              index += 1;
              return { done: false, value };
            },
          };
        },
      },
      text: async () => '',
      json: async () => ({}),
    })) as unknown as typeof fetch;

    let seen = '';
    const result = await requestStream('/chat/completions', {}, (chunk, fullText) => {
      seen += chunk;
      expect(fullText).toBe('OK');
    });

    expect(seen).toBe('OK');
    expect(result).toBe('OK');
  });

  test('requestStream extracts assistant text from json fallback responses', async () => {
    const source = `${extractHelpers()} return requestStream;`;
    const factory = new Function(source);
    const requestStream = factory() as (url: string, options?: object, onChunk?: (chunk: string, fullText: string) => void) => Promise<string>;

    global.fetch = jest.fn(async () => ({
      ok: true,
      headers: { get: () => 'application/json; charset=utf-8' },
      body: null,
      text: async () => JSON.stringify({
        choices: [{
          message: {
            role: 'assistant',
            content: 'answer-json',
          },
        }],
      }),
      json: async () => ({
        choices: [{
          message: {
            role: 'assistant',
            content: 'answer-json',
          },
        }],
      }),
    })) as unknown as typeof fetch;

    const result = await requestStream('/chat/completions');

    expect(result).toBe('answer-json');
  });
});
