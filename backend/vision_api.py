"""
大模型图片理解小模块 - 调用智谱 GLM-4V 对图片进行描述/判断。
API Key 从环境变量 BIGMODEL_API_KEY 读取，请勿写死在代码中。
支持单图或多图（多图时模型会同时看到多张图并一起回答）。

Lovart 等外网图片：请由挂翻墙的客户端拉图后传 image_base64_list，服务端不通过代理访问外网。
智谱仅支持 jpg/png/jpeg，若图床返回 webp 则在内存中转为 PNG 再传。
"""
import base64
import io
import os
import requests
from typing import Union
from urllib.parse import urlparse

try:
    from PIL import Image
except ImportError:
    Image = None

URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
# 默认用 GLM-4.6V 旗舰版（走资源包）；可改为 glm-4v-flash 使用免费版
DEFAULT_MODEL = "glm-4.6v"

# 这些域名的图片服务端不拉取，须由客户端拉图后传 base64
CLIENT_FETCH_HOST_SUFFIXES = ("lovart.ai",)

# 智谱对单图/请求体有大小限制，过大的 data URL 先缩图再传（避免 1210 参数错误）
VISION_MAX_DATA_URL_BYTES = 4 * 1024 * 1024   # 4MB
VISION_RESIZE_MAX_PIXEL = 1024

# 服务端拉图时使用的头（仅用于非 Lovart 等直连可达的 URL），模拟浏览器以通过防盗链
FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.lovart.ai/",
}


def get_api_key():
    """从环境变量读取 API Key，未配置时返回 None。"""
    return os.getenv("BIGMODEL_API_KEY") or os.getenv("GLM_API_KEY")


def _must_client_fetch(url: str) -> bool:
    """判断该 URL 是否须由客户端拉图传 base64（服务端不通过代理访问）。"""
    try:
        parsed = urlparse(url.strip())
        host = (parsed.netloc or "").lower()
        return any(host.endswith(s) or host == s for s in CLIENT_FETCH_HOST_SUFFIXES)
    except Exception:
        return False


def _webp_bytes_to_png_base64(data: bytes) -> str | None:
    """内存中把 WebP 转为 PNG 的 base64，失败返回 None。"""
    if not Image:
        return None
    try:
        img = Image.open(io.BytesIO(data))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None


def _fetch_image_as_base64(url: str, timeout: int = 15):
    """
    在内存中拉取图片并转为 base64，不写本地文件。
    单次 15s、最多重试 1 次，拉不到约 30s 内返回错误，避免客户端等满 60s 才超时。
    成功返回 (True, base64_str, mime, None)；失败返回 (False, None, None, error_msg)。
    智谱仅支持 jpg/png/jpeg，若图床返回 webp 则转为 PNG。
    """
    fetch_url = url
    if "x-oss-process=image" in url and "format,webp" in url:
        fetch_url = url.replace("format,webp", "format,png")
    last_err = None
    for attempt in range(2):
        try:
            r = requests.get(
                fetch_url,
                headers=FETCH_HEADERS,
                timeout=timeout,
            )
            if r.status_code != 200 or not r.content:
                last_err = f"HTTP {r.status_code}" if r.status_code != 200 else "响应为空"
                return False, None, None, last_err
            ct = (r.headers.get("Content-Type") or "").lower()
            data = r.content
            if "image/webp" in ct or (len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"):
                png_b64 = _webp_bytes_to_png_base64(data)
                if png_b64:
                    return True, png_b64, "image/png", None
                return False, None, None, "WebP 转 PNG 失败"
            if "image/jpeg" in ct or "image/jpg" in ct:
                mime = "image/jpeg"
            else:
                mime = "image/png"
            return True, base64.b64encode(data).decode("ascii"), mime, None
        except requests.exceptions.Timeout as e:
            last_err = f"超时: {e}"
        except requests.exceptions.SSLError as e:
            last_err = f"SSL 错误: {e}"
        except requests.exceptions.ConnectionError as e:
            last_err = f"连接失败: {e}"
        except Exception as e:
            last_err = str(e)
        if attempt == 0:
            continue
    return False, None, None, last_err or "未知错误"


def _shrink_large_data_url(data_url: str) -> str:
    """
    若 data URL 过大（超过 VISION_MAX_DATA_URL_BYTES），解码后缩图再编码为 JPEG，避免智谱 1210 参数错误。
    返回缩小后的 data URL，失败或无需缩小时返回原串。
    """
    if not data_url or not data_url.startswith("data:image/") or ";base64," not in data_url:
        return data_url
    if len(data_url) <= VISION_MAX_DATA_URL_BYTES:
        return data_url
    if not Image:
        return data_url
    try:
        header, b64 = data_url.split(",", 1)
        raw = base64.b64decode(b64)
        img = Image.open(io.BytesIO(raw))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        w, h = img.size
        if w <= VISION_RESIZE_MAX_PIXEL and h <= VISION_RESIZE_MAX_PIXEL:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            new_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return f"data:image/jpeg;base64,{new_b64}"
        ratio = min(VISION_RESIZE_MAX_PIXEL / w, VISION_RESIZE_MAX_PIXEL / h)
        nw, nh = int(w * ratio), int(h * ratio)
        resample = getattr(Image, "Resampling", None) and Image.Resampling.LANCZOS or Image.LANCZOS
        img = img.resize((nw, nh), resample)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        new_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{new_b64}"
    except Exception:
        return data_url


def _resolve_image_for_api(raw_url: str):
    """
    解析出传给智谱的「图片内容」：直连可达的 URL 原样返回；Lovart 等须客户端传 base64，服务端不拉取。
    """
    u = (raw_url or "").strip()
    if not u.startswith(("http://", "https://")):
        return u, None
    if _must_client_fetch(u):
        return None, "Lovart 等外网图片请由挂翻墙的客户端拉图后传 image_base64_list，服务端不通过代理访问"
    ok, b64, mime, err = _fetch_image_as_base64(u)
    if not ok or not b64:
        return None, (err or "拉图失败")
    return f"data:{mime};base64,{b64}", None


def describe_image(
    image_url: Union[str, list[str]],
    prompt: str = "请描述这张图片的内容",
    model: Union[str, None] = None,
    response_format_json: bool = False,
    api_key: Union[str, None] = None,
):
    """
    调用智谱视觉模型对一张或多张图片进行理解，返回模型回复文本。

    :param image_url: 图片 URL（字符串）或 URL 列表，需公网可访问；或 data:image/...;base64,...
    :param prompt: 向模型提问的文本；多图时可用如「请分别描述这几张图」等。若 response_format_json=True，建议在 prompt 中写明期望的 JSON 结构。
    :param model: 模型名，如 glm-4.6v（资源包）、glm-4v-flash（免费）。None 或空则用 DEFAULT_MODEL。
    :param response_format_json: 为 True 时请求智谱按 JSON 输出（response_format.json_object），便于程序解析；结构约束需在 prompt 中说明。
    :param api_key: 可选，传入时优先使用（如从配置表读取）；否则用 get_api_key()。
    :return: (success: bool, result: str | dict)
        success 为 True 时 result 为回复文本；为 False 时 result 为错误信息或原始响应
    """
    api_key = (api_key or "").strip() or get_api_key()
    if not api_key:
        return False, "未配置 BIGMODEL_API_KEY，请在环境变量或 .env 中设置"
    if not (model or "").strip():
        model = DEFAULT_MODEL

    urls = [image_url] if isinstance(image_url, str) else list(image_url)
    if not urls:
        return False, "未提供任何图片 URL"

    content = [{"type": "text", "text": prompt}]
    for u in urls:
        u = (u or "").strip()
        if not u:
            continue
        # 客户端直接传的 data URL 不再拉图，避免容器内 Network unreachable
        if u.startswith("data:image/"):
            u = _shrink_large_data_url(u)  # 过大时缩图，避免智谱 1210
            content.append({"type": "image_url", "image_url": {"url": u}})
        elif u.startswith(("http://", "https://")):
            resolved, err = _resolve_image_for_api(u)
            if err is not None:
                return False, f"无法拉取该图片: {err}"
            resolved = _shrink_large_data_url(resolved)
            content.append({"type": "image_url", "image_url": {"url": resolved}})

    if len(content) == 1:
        return False, "没有有效的图片（需 image_url / image_urls 或 image_base64 / image_base64_list）"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    data = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
    }
    if response_format_json:
        data["response_format"] = {"type": "json_object"}

    try:
        resp = requests.post(URL, headers=headers, json=data, timeout=60)
        body = resp.json()
    except requests.RequestException as e:
        return False, str(e)
    except ValueError:
        return False, resp.text if hasattr(resp, "text") else "响应非 JSON"

    if resp.status_code != 200:
        return False, body.get("error", body)

    choices = body.get("choices")
    if not choices or not isinstance(choices, list):
        return False, body
    msg = choices[0].get("message") or {}
    content = msg.get("content") or ""
    return True, content.strip()
