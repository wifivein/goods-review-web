"""
实验：让智谱 API 能「读到」Lovart 预览图。
仅做测试，不修改 vision_api.py / app.py。
尝试多种方式，看哪种能让大模型成功看到图片内容。
"""
import base64
import os
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
_env_path = os.path.join(_script_dir, ".env")


def _load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=_env_path)
    except ImportError:
        pass
    if not os.environ.get("BIGMODEL_API_KEY") and os.path.isfile(_env_path):
        with open(_env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k == "BIGMODEL_API_KEY" and v:
                        os.environ[k] = v
                        break


_load_env()
sys.path.insert(0, _script_dir)

import requests

# 智谱 API（与 vision_api 一致）
ZHIPU_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
ZHIPU_MODEL = "glm-4v-flash"

# Lovart 示例图（与 test_vision_api 里一致）
LOVART_SAMPLE_URL = (
    "https://a.lovart.ai/artifacts/agent/cPtKDfLEOaNF9sHM.png"
    "?x-oss-process=image/resize,w_512,m_lfit/format,webp"
)
LOVART_SAMPLE_URL_NO_QUERY = "https://a.lovart.ai/artifacts/agent/cPtKDfLEOaNF9sHM.png"

# 桌面浏览器 UA / Referer，模拟「你们预览页」
DESKTOP_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REFERER_LOVART = "https://www.lovart.ai/"
REFERER_LOVART_ROOT = "https://lovart.ai/"


def get_api_key():
    return os.environ.get("BIGMODEL_API_KEY") or os.environ.get("GLM_API_KEY")


def call_zhipu_with_url(image_url: str, prompt: str = "请用一句话描述这张图片的内容。"):
    """直接传 URL 给智谱（与 vision_api 行为一致）。"""
    from vision_api import describe_image
    return describe_image(image_url, prompt=prompt)


def call_zhipu_with_base64(image_base64: str, prompt: str = "请用一句话描述这张图片的内容。"):
    """把 base64 图片传给智谱（智谱文档支持 image_url.url 为 base64）。"""
    api_key = get_api_key()
    if not api_key:
        return False, "未配置 BIGMODEL_API_KEY"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    content = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": image_base64}},
    ]
    data = {
        "model": ZHIPU_MODEL,
        "messages": [{"role": "user", "content": content}],
    }
    try:
        resp = requests.post(ZHIPU_URL, headers=headers, json=data, timeout=60)
        body = resp.json()
    except requests.RequestException as e:
        return False, str(e)
    except ValueError:
        return False, getattr(resp, "text", "非 JSON")
    if resp.status_code != 200:
        return False, body.get("error", body)
    choices = body.get("choices") or []
    if not choices:
        return False, body
    msg = (choices[0] or {}).get("message") or {}
    text = (msg.get("content") or "").strip()
    return True, text


def fetch_image_as_base64(
    url: str,
    referer: str | None = REFERER_LOVART,
    user_agent: str = DESKTOP_UA,
) -> tuple:
    """
    用指定 Referer/UA 拉图，成功则返回 (True, base64_string)，失败返回 (False, error_msg)。
    referer 为 None 或空时不带 Referer 头。
    """
    headers = {"User-Agent": user_agent}
    if referer:
        headers["Referer"] = referer
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        raw = r.content
        if not raw:
            return False, "空响应"
        return True, base64.b64encode(raw).decode("ascii")
    except requests.RequestException as e:
        return False, str(e)


def run_experiment(name: str, run_fn):
    print(f"\n{'='*60}")
    print(f"【{name}】")
    print("=" * 60)
    try:
        ok, out = run_fn()
        if ok:
            print("结果: 成功")
            print(out[:500] + ("..." if len(out) > 500 else ""))
        else:
            print("结果: 失败")
            print(out)
    except Exception as e:
        print("结果: 异常")
        print(e)


def main():
    if not get_api_key():
        print("错误：未设置 BIGMODEL_API_KEY，请在 .env 或环境变量中配置。")
        sys.exit(1)

    print("Lovart 示例 URL:", LOVART_SAMPLE_URL[:80], "...")

    # 实验 1：直接传 Lovart URL 给智谱（预期可能失败：智谱服务器拉不到图）
    run_experiment(
        "实验1 - 直接传 Lovart URL 给智谱",
        lambda: call_zhipu_with_url(LOVART_SAMPLE_URL),
    )

    # 实验 2：本机用 Referer + 桌面 UA 拉图，转 base64 再调智谱
    def exp2():
        ok, data = fetch_image_as_base64(LOVART_SAMPLE_URL, referer=REFERER_LOVART)
        if not ok:
            return False, f"拉图失败: {data}"
        return call_zhipu_with_base64(data)

    run_experiment(
        "实验2 - 本机带 Referer(www.lovart.ai) + 桌面 UA 拉图 → base64 → 智谱",
        exp2,
    )

    # 实验 3：同上，但 Referer 用 https://lovart.ai/
    def exp3():
        ok, data = fetch_image_as_base64(LOVART_SAMPLE_URL, referer=REFERER_LOVART_ROOT)
        if not ok:
            return False, f"拉图失败: {data}"
        return call_zhipu_with_base64(data)

    run_experiment(
        "实验3 - 本机带 Referer(lovart.ai) + 桌面 UA 拉图 → base64 → 智谱",
        exp3,
    )

    # 实验 4：去掉 URL 的 query（只保留基础 URL）再拉图
    def exp4():
        ok, data = fetch_image_as_base64(LOVART_SAMPLE_URL_NO_QUERY, referer=REFERER_LOVART)
        if not ok:
            return False, f"拉图失败: {data}"
        return call_zhipu_with_base64(data)

    run_experiment(
        "实验4 - 无 query 的 Lovart URL，带 Referer 拉图 → base64 → 智谱",
        exp4,
    )

    # 实验 5：不带 Referer 拉图（确认是否防盗链）
    def exp5():
        ok, data = fetch_image_as_base64(
            LOVART_SAMPLE_URL,
            referer="",
        )
        if not ok:
            return False, f"拉图失败(无 Referer): {data}"
        return call_zhipu_with_base64(data)

    run_experiment(
        "实验5 - 本机无 Referer 拉图 → 若拉得到则 base64 → 智谱",
        exp5,
    )

    print("\n" + "=" * 60)
    print("实验结束。若实验2/3/4 任一成功，说明「本机代理拉图 + base64 给智谱」可行。")
    print("=" * 60)


if __name__ == "__main__":
    main()
