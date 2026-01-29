"""
测试大模型图片理解：调用 GLM-4V 对指定图片 URL 进行描述。
使用前请设置环境变量 BIGMODEL_API_KEY，或在项目根目录的 .env 中配置。

示例：
  python test_vision_api.py
  python test_vision_api.py "http://example.com/1.jpg"
  python test_vision_api.py "http://a.jpg" "http://b.jpg" "http://c.jpg"
  python test_vision_api.py "图1.jpg" "图2.jpg" -p "请分别描述这几张图"
"""
import argparse
import os
import sys

# 先加载与本脚本同目录的 .env，再导入 vision_api（否则 get_api_key 读不到）
_script_dir = os.path.dirname(os.path.abspath(__file__))
_env_path = os.path.join(_script_dir, ".env")

def _load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=_env_path)
    except ImportError:
        pass
    # 若仍未设置且 .env 存在，则手动解析（兼容部分环境下 dotenv 不生效）
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
from vision_api import describe_image, get_api_key


SAMPLE_IMAGE_URL = (
    "https://a.lovart.ai/artifacts/agent/cPtKDfLEOaNF9sHM.png"
    "?x-oss-process=image/resize,w_512,m_lfit/format,webp"
)


def main():
    parser = argparse.ArgumentParser(description="调用 GLM-4V 对一张或多张图片 URL 进行描述")
    parser.add_argument(
        "url",
        nargs="*",
        default=None,
        help="一张或多张图片 URL，不传则使用内置示例 URL",
    )
    parser.add_argument(
        "-p", "--prompt",
        default=None,
        help="发给模型的提示词；不传时单图用「请描述这张图片的内容」，多图用「请分别描述这几张图片的内容」",
    )
    args = parser.parse_args()

    urls = args.url if args.url else [SAMPLE_IMAGE_URL]
    for u in urls:
        if not u or not u.strip().startswith(("http://", "https://")):
            print("错误：请提供有效的 http/https 图片 URL")
            sys.exit(1)

    if not get_api_key():
        print("错误：未设置 BIGMODEL_API_KEY。请在 .env 或环境变量中配置。")
        sys.exit(1)

    prompt = args.prompt
    if prompt is None:
        prompt = "请分别描述这几张图片的内容" if len(urls) > 1 else "请描述这张图片的内容"

    print("正在调用 GLM-4V 分析图片...")
    print("图片数量:", len(urls))
    for i, u in enumerate(urls, 1):
        print(f"  [{i}] {u[:80]}{'...' if len(u) > 80 else ''}")
    success, result = describe_image(urls, prompt=prompt)
    if success:
        print("--- 模型回复 ---")
        print(result)
    else:
        print("--- 失败 ---")
        print(result)
        sys.exit(1)


if __name__ == "__main__":
    main()
