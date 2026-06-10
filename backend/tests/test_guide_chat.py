import os
import sys
import unittest

BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, BACKEND_DIR)

from services.guide import guide_chat, guide_chat_events, get_guide_llm_config


class GuideChatTest(unittest.TestCase):
    def setUp(self):
        self.stores = [
            {
                'id': 1,
                'name': '武汉热辣火锅',
                'category': '火锅',
                'address': '武汉 江汉路',
                'avg_price': 88,
                'rating': 4.8,
                'confidence': 0.9,
                'blogger_name': '真探唐仁杰',
                'tags': ['本地特色', '不踩雷'],
                'recommend_dishes': ['牛油锅底'],
            }
        ]

    def test_clarifies_when_model_asks_question(self):
        def fake_llm(messages, **kwargs):
            return {
                'content': '{"need_clarification": true, "clarifying_question": "你想在哪个城市找？", "intent": {}}'
            }

        result = guide_chat(self.stores, [{'role': 'user', 'content': '推荐点好吃的'}], llm_func=fake_llm)

        self.assertEqual(result['mode'], 'clarify')
        self.assertEqual(result['reply'], '你想在哪个城市找？')
        self.assertEqual(result['recommendations'], [])

    def test_uses_model_intent_and_model_reply(self):
        calls = []

        def fake_llm(messages, **kwargs):
            calls.append(messages[0]['content'])
            if 'JSON Schema' in messages[0]['content']:
                return {
                    'content': '{"need_clarification": false, "intent": {"city": "武汉", "category": "火锅", "budget": 100, "preferences": ["不踩雷"]}}'
                }
            return {'content': '我按武汉火锅和人均100以内筛了一下，优先推荐武汉热辣火锅。'}

        result = guide_chat(
            self.stores,
            [{'role': 'user', 'content': '不要太贵，想吃不踩雷的'}],
            llm_func=fake_llm,
        )

        self.assertEqual(result['recommendations'][0]['id'], 1)
        self.assertIn('武汉热辣火锅', result['reply'])
        self.assertEqual(len(calls), 2)

    def test_guide_config_falls_back_to_base_llm(self):
        api_url, api_key, model = get_guide_llm_config()
        self.assertTrue(api_url)
        self.assertTrue(model)
        self.assertIsInstance(api_key, str)

    def test_stream_events_include_meta_delta_done(self):
        events = list(guide_chat_events(
            self.stores,
            [{'role': 'user', 'content': '武汉火锅人均100以内不踩雷'}],
        ))
        event_types = [event['type'] for event in events]
        self.assertIn('meta', event_types)
        self.assertIn('delta', event_types)
        self.assertEqual(event_types[-1], 'done')


if __name__ == '__main__':
    unittest.main()
