import sys; sys.path.insert(0,'backend')
from services.analyzer import parse_llm_response

# 模拟各种常见的 LLM JSON 问题
tests = [
    # 测试1: 末尾多逗号
    ('{"stores": [{"name": "测试店", "tags": ["火锅", "排队王", ], "rating": 4, }]}', True),
    # 测试2: JSON 正常
    ('{"stores": [{"name": "正常店", "rating": 5, "tags": ["a", "b"]}]}', True),
    # 测试3: 代码块包裹
    ('```json\n{"stores": [{"name": "代码块店", "rating": 3}]}\n```', True),
    # 测试4: 截断的 JSON（模拟 max_tokens 不够）
    ('{"stores": [{"name": "德华兴", "category": "面馆", "city": "晋城", "avg_price": 248, "rating": 3, "recommend_di', True),
    # 测试5: 截断
    ('{"stores": [{"name": "店A", "rating": 4}, {"name": "店B", "rating": 3', True),
]

for i, (test, expect_ok) in enumerate(tests):
    result = parse_llm_response(test)
    stores = len(result.get('stores', [])) if result else 0
    status = "OK" if (result is not None) == expect_ok else "UNEXPECTED"
    print(f'测试{i+1}: stores={stores} {status}')
    if result:
        for s in result.get('stores', []):
            print(f'  - {s.get("name", "?")}')
