import os
import sys
import unittest

BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, BACKEND_DIR)

from services.recommender import parse_intent, recommend_for_query


class RecommenderTest(unittest.TestCase):
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
                'lat': 30.58,
                'lng': 114.28,
            },
            {
                'id': 2,
                'name': '成都甜品铺',
                'category': '甜品饮品',
                'address': '成都 春熙路',
                'avg_price': 35,
                'rating': 4.6,
                'confidence': 0.8,
                'blogger_name': '大祥哥',
                'tags': ['拍照'],
                'recommend_dishes': ['冰粉'],
                'lat': 30.65,
                'lng': 104.08,
            },
            {
                'id': 3,
                'name': '武汉普通火锅',
                'category': '火锅',
                'address': '武汉 光谷',
                'avg_price': 180,
                'rating': 3.5,
                'confidence': 0.6,
                'blogger_name': '其他博主',
                'tags': [],
                'recommend_dishes': [],
                'lat': 30.50,
                'lng': 114.40,
            },
        ]

    def test_parse_budget_and_category(self):
        intent = parse_intent('武汉两个人想吃火锅，人均100以内，不踩雷')
        self.assertEqual(intent['city'], '武汉')
        self.assertEqual(intent['category'], '火锅')
        self.assertEqual(intent['budget'], 100)
        self.assertTrue(intent['flags']['safe'])

    def test_recommend_filters_by_city_and_category(self):
        result = recommend_for_query(self.stores, '武汉火锅人均100以内不踩雷')
        ids = [item['id'] for item in result['recommendations']]
        self.assertEqual(ids[0], 1)
        self.assertNotIn(2, ids)

    def test_nearby_prefers_shorter_distance(self):
        result = recommend_for_query(
            self.stores,
            '附近火锅',
            user_location={'lat': 30.58, 'lng': 114.28},
        )
        self.assertEqual(result['recommendations'][0]['id'], 1)
        self.assertIn('距离约', result['recommendations'][0]['reason'])


if __name__ == '__main__':
    unittest.main()
