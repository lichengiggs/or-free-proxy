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
