#!/usr/bin/env python3

import json
import time
import sys
from datetime import datetime

try:
    import requests
except ImportError:
    print("请先安装requests库: pip install requests")
    sys.exit(1)

BASE_URL = "http://localhost:8765/v1"
API_KEY = "test-api-key"

def test_api(task_num, task_type, messages):
    print(f"\n{'='*60}")
    print(f"测试 {task_num}/10: {task_type}")
    print(f"{'='*60}")
    
    payload = {
        "model": "test-model",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 200
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    start_time = time.time()
    
    try:
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        
        elapsed_time = time.time() - start_time
        
        print(f"⏱️  响应时间: {elapsed_time:.2f}秒")
        print(f"📊 HTTP状态码: {response.status_code}")
        
        actual_model = response.headers.get('X-Actual-Model', 'unknown')
        fallback_used = response.headers.get('X-Fallback-Used')
        fallback_reason = response.headers.get('X-Fallback-Reason')
        
        print(f"🤖 实际使用模型: {actual_model}")
        if fallback_used:
            print(f"⚠️  使用了Fallback: {fallback_reason}")
        
        if response.status_code == 200:
            data = response.json()
            if 'choices' in data and len(data['choices']) > 0:
                content = data['choices'][0]['message']['content']
                print(f"\n💬 AI回复:\n{content}")
                return True, elapsed_time, actual_model
            else:
                print(f"❌ 响应格式异常: {json.dumps(data, indent=2)}")
                return False, elapsed_time, actual_model
        else:
            print(f"❌ 请求失败: {response.text}")
            return False, elapsed_time, actual_model
            
    except requests.exceptions.ConnectionError:
        print(f"❌ 连接失败: 请确保代理服务已启动 (npm start)")
        return False, 0, None
    except requests.exceptions.Timeout:
        print(f"❌ 请求超时")
        return False, 0, None
    except Exception as e:
        print(f"❌ 异常: {e}")
        return False, 0, None

def main():
    print("🚀 OpenRouter Free Proxy 测试程序")
    print(f"代理地址: {BASE_URL}")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    tasks = [
        ("基础问答", [{"role": "user", "content": "1 + 1 等于几？只回答数字"}]),
        ("英文翻译", [{"role": "user", "content": "把'你好世界'翻译成英文，只回答翻译结果"}]),
        ("代码解释", [{"role": "user", "content": "解释Python的print('Hello')是做什么的，用一句话说明"}]),
        ("逻辑推理", [{"role": "user", "content": "如果A比B高，B比C高，那么A和C谁高？只回答名字"}]),
        ("单位换算", [{"role": "user", "content": "1公里等于多少米？只回答数字"}]),
        ("日期计算", [{"role": "user", "content": "一周有几天？只回答数字"}]),
        ("常识问答", [{"role": "user", "content": "太阳从哪个方向升起？只回答方向"}]),
        ("简单编程", [{"role": "user", "content": "写一个Python列表[1,2,3]的写法，只回答代码"}]),
        ("数学计算", [{"role": "user", "content": "10的平方是多少？只回答数字"}]),
        ("文字生成", [{"role": "user", "content": "用3个词描述人工智能"}])
    ]
    
    results = []
    models_used = set()
    
    for i, (task_type, messages) in enumerate(tasks, 1):
        success, elapsed, model = test_api(i, task_type, messages)
        results.append((success, elapsed))
        if model:
            models_used.add(model)
        
        if i < 10:
            time.sleep(1)
    
    print(f"\n{'='*60}")
    print("📈 测试结果统计")
    print(f"{'='*60}")
    
    success_count = sum(1 for r in results if r[0])
    total_time = sum(r[1] for r in results)
    avg_time = total_time / len(results) if results else 0
    
    print(f"✅ 成功: {success_count}/10")
    print(f"❌ 失败: {10 - success_count}/10")
    print(f"⏱️  总耗时: {total_time:.2f}秒")
    print(f"⏱️  平均响应: {avg_time:.2f}秒")
    print(f"🤖 使用过的模型: {', '.join(models_used) if models_used else 'N/A'}")
    
    if success_count == 10:
        print("\n🎉 完美！所有测试通过，代理工作正常！")
    elif success_count >= 7:
        print("\n✅ 良好！大部分测试通过，代理基本可用")
    elif success_count >= 4:
        print("\n⚠️  部分测试失败，可能需要检查代理配置")
    else:
        print("\n❌ 大量测试失败，请检查代理服务是否正常")
    
    return success_count

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success >= 7 else 1)
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        sys.exit(1)
