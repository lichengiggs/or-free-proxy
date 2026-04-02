from __future__ import annotations

import json
import unittest

from python_scripts.response_normalizer import normalize_json_success, normalize_provider_response, sanitize_model_text


class ResponseNormalizerTests(unittest.TestCase):
    def test_keeps_json_success_as_openai_json(self) -> None:
        response = normalize_json_success(provider='openrouter', model='m1', content='hello')
        parsed = json.loads(response.body.decode('utf-8'))
        self.assertEqual(parsed['choices'][0]['message']['content'], 'hello')

    def test_sanitizes_longcat_tool_call_markers_into_questions(self) -> None:
        raw = (
            '我理解您的意图。\n'
            'question\n'
            '<longcat_arg_key>questions</longcat_arg_key>'
            '<longcat_arg_value>{"question": "您当前的核心目标是什么？", "header": "项目背景"}, {"question": "您最在意什么指标？", "header": "质量关注点"}</longcat_arg_value>'
            '<longcat_tool_call>'
        )
        cleaned = sanitize_model_text(raw)
        self.assertIn('我理解您的意图。', cleaned)
        self.assertIn('1. 项目背景：您当前的核心目标是什么？', cleaned)
        self.assertIn('2. 质量关注点：您最在意什么指标？', cleaned)
        self.assertNotIn('<longcat_tool_call>', cleaned)

    def test_normalizes_longcat_tool_call_to_openai_tool_calls(self) -> None:
        body = (
            '{"choices":[{"message":{"content":"question\\n<longcat_tool_call><longcat_arg_key>questions</longcat_arg_key>'
            '<longcat_arg_value>{\\"question\\": \\"您最在意什么指标？\\", \\"header\\": \\"质量关注点\\"}</longcat_arg_value>'
            '</longcat_tool_call>"}}]}'
        ).encode('utf-8')
        response = normalize_provider_response(provider='longcat', model='LongCat-Flash-Lite', body=body, stream=False)
        parsed = json.loads(response.body.decode('utf-8'))
        message = parsed['choices'][0]['message']
        self.assertIsNone(message['content'])
        self.assertIn('tool_calls', message)
        self.assertEqual(message['tool_calls'][0]['function']['name'], 'question')

    def test_sse_termination_contains_done(self) -> None:
        from python_scripts.response_normalizer import wrap_openai_body_as_sse
        body = json.dumps({
            'choices': [{'message': {'content': 'hi', 'role': 'assistant'}, 'finish_reason': 'stop'}]
        }).encode()
        chunks = list(wrap_openai_body_as_sse(provider='longcat', fallback_model='longcat/LongCat-Flash', body=body))
        last = chunks[-1]
        self.assertIn(b'[DONE]', last)

    def test_sse_chunks_are_valid_json_lines(self) -> None:
        from python_scripts.response_normalizer import wrap_openai_body_as_sse
        body = json.dumps({
            'id': 'test-123',
            'model': 'longcat/LongCat-Flash',
            'choices': [{'message': {'content': 'hello', 'role': 'assistant'}, 'finish_reason': 'stop'}]
        }).encode()
        chunks = list(wrap_openai_body_as_sse(provider='longcat', fallback_model='longcat/LongCat-Flash', body=body))
        for chunk in chunks:
            line = chunk.decode('utf-8').strip()
            self.assertTrue(line.startswith('data: '))
            payload = line[6:]
            if payload != '[DONE]':
                json.loads(payload)

    def test_normalize_provider_response_stream_false(self) -> None:
        body = json.dumps({
            'choices': [{'message': {'content': 'ok', 'role': 'assistant'}, 'finish_reason': 'stop'}]
        }).encode()
        resp = normalize_provider_response(provider='longcat', model='LongCat-Flash', body=body, stream=False)
        self.assertEqual(resp.status, 200)
        self.assertIn(b'application/json', resp.headers.get('Content-Type', '').encode())
        parsed = json.loads(resp.body)
        self.assertEqual(parsed['choices'][0]['message']['content'], 'ok')

    def test_normalize_provider_response_stream_true(self) -> None:
        body = json.dumps({
            'choices': [{'message': {'content': 'ok', 'role': 'assistant'}, 'finish_reason': 'stop'}]
        }).encode()
        resp = normalize_provider_response(provider='longcat', model='LongCat-Flash', body=body, stream=True)
        self.assertEqual(resp.status, 200)
        self.assertIn(b'text/event-stream', resp.headers.get('Content-Type', '').encode())
        self.assertIsNotNone(resp.stream_chunks)
