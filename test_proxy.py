#!/usr/bin/env python3

import argparse
import json
import sys
import time
from datetime import datetime

try:
    import requests
except ImportError:
    print("请先安装 requests：pip install requests")
    sys.exit(1)

DEFAULT_BASE_URL = "http://localhost:8765"
DEFAULT_API_KEY = "test-api-key"
DEFAULT_MODEL = "openrouter/auto:free"


def build_parser():
    parser = argparse.ArgumentParser(description="Free Proxy 联调脚本")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="服务地址，默认 http://localhost:8765")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="客户端侧任意非空 key")
    parser.add_argument("--model", default="", help="指定模型；不填则使用 /admin/models 返回的当前模型")
    parser.add_argument("--count", type=int, default=10, help="测试轮数，默认 10")
    return parser


def request_json(method, url, **kwargs):
    response = requests.request(method, url, timeout=60, **kwargs)
    try:
      data = response.json()
    except Exception:
      data = None
    return response, data


def fetch_model_status(base_url):
    response, data = request_json("GET", f"{base_url}/admin/models")
    if not response.ok:
        raise RuntimeError(f"获取模型列表失败: {response.status_code} {response.text}")
    return data or {}


def pick_model(status, forced_model):
    if forced_model:
        return forced_model
    current = status.get("current")
    if isinstance(current, str) and current.strip():
        return current
    recommended = status.get("recommended")
    if isinstance(recommended, str) and recommended.strip():
        return recommended
    return DEFAULT_MODEL


def test_api(base_url, api_key, model, task_num, task_type, messages):
    print(f"\n{'=' * 60}")
    print(f"测试 {task_num}: {task_type}")
    print(f"{'=' * 60}")

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 200,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    start_time = time.time()

    try:
        response, data = request_json(
            "POST",
            f"{base_url}/v1/chat/completions",
            headers=headers,
            json=payload,
        )
        elapsed_time = time.time() - start_time

        print(f"⏱️  响应时间: {elapsed_time:.2f} 秒")
        print(f"📊 HTTP 状态码: {response.status_code}")

        actual_model = response.headers.get("X-Actual-Model", "unknown")
        fallback_used = response.headers.get("X-Fallback-Used")
        fallback_reason = response.headers.get("X-Fallback-Reason")

        print(f"🤖 请求模型: {model}")
        print(f"🤖 实际模型: {actual_model}")
        if fallback_used:
            print(f"⚠️  已 fallback: {fallback_reason or 'unknown'}")

        if response.ok and data:
            choices = data.get("choices") or []
            if choices:
                content = choices[0].get("message", {}).get("content", "")
                print(f"\n💬 回复:\n{content}")
                return True, elapsed_time, actual_model
            print(f"❌ 响应格式异常: {json.dumps(data, ensure_ascii=False, indent=2)}")
            return False, elapsed_time, actual_model

        print(f"❌ 请求失败: {response.text}")
        return False, elapsed_time, actual_model

    except requests.exceptions.ConnectionError:
        print("❌ 连接失败：请先启动服务（npm start）")
        return False, 0, None
    except requests.exceptions.Timeout:
        print("❌ 请求超时")
        return False, 0, None
    except Exception as exc:
        print(f"❌ 异常: {exc}")
        return False, 0, None


def main():
    args = build_parser().parse_args()
    base_url = args.base_url.rstrip("/")

    print("🚀 Free Proxy 联调脚本")
    print(f"代理地址: {base_url}")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        model_status = fetch_model_status(base_url)
    except Exception as exc:
        print(f"❌ 无法获取模型状态: {exc}")
        return 1

    chosen_model = pick_model(model_status, args.model)
    print(f"当前模型: {model_status.get('current', 'N/A')}")
    print(f"推荐模型: {model_status.get('recommended', 'N/A')}")
    print(f"本次使用: {chosen_model}")

    tasks = [
        ("基础问答", [{"role": "user", "content": "1 + 1 等于几？只回答数字"}]),
        ("代码解释", [{"role": "user", "content": "解释 Python 的 print('Hello') 是做什么的，用一句话说明"}])
    ][: max(1, args.count)]

    results = []
    models_used = set()

    for index, (task_type, messages) in enumerate(tasks, 1):
        success, elapsed, actual_model = test_api(base_url, args.api_key, chosen_model, index, task_type, messages)
        results.append((success, elapsed))
        if actual_model:
            models_used.add(actual_model)
        if index < len(tasks):
            time.sleep(1)

    print(f"\n{'=' * 60}")
    print("📈 测试结果统计")
    print(f"{'=' * 60}")

    success_count = sum(1 for success, _ in results if success)
    total_time = sum(elapsed for _, elapsed in results)
    avg_time = total_time / len(results) if results else 0

    print(f"✅ 成功: {success_count}/{len(results)}")
    print(f"❌ 失败: {len(results) - success_count}/{len(results)}")
    print(f"⏱️  总耗时: {total_time:.2f} 秒")
    print(f"⏱️  平均响应: {avg_time:.2f} 秒")
    print(f"🤖 实际使用过的模型: {', '.join(sorted(models_used)) if models_used else 'N/A'}")

    if success_count == len(results):
        print("\n🎉 所有测试通过，代理工作正常")
    elif success_count >= max(1, len(results) // 2):
        print("\n✅ 大部分测试通过，代理基本可用")
    else:
        print("\n❌ 失败较多，请检查服务、Key 和 fallback 配置")

    return 0 if success_count >= max(1, len(results) // 2) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        sys.exit(1)
