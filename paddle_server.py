# -*- coding: utf-8 -*-
"""
豆包视觉 API 代理服务
为牛蛙收购单 OCR 识别页面提供后端代理，转发请求到火山引擎方舟 API。
同时托管前端页面与静态资源（同源部署，避免 CORS / IPv6 解析问题）。
"""
import sys
import time
import json
import traceback
import logging
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from flask import Flask, request, jsonify, send_from_directory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("doubao-proxy")

BASE_DIR = __file__ if "__file__" in globals() else "."
BASE_DIR = __import__("os").path.dirname(__import__("os").path.abspath(BASE_DIR))

# 仅允许这些静态资源被访问，避免泄露源码 / 任意文件读取
ALLOWED_STATIC = {"index.html", "xlsx-js-style.js"}

# 仅允许转发到火山引擎方舟域名，避免成为任意 URL 的开放代理（SSRF 防护）
ALLOWED_HOST_SUFFIXES = ("volces.com", "volcengineapi.com")

DEFAULT_ARK_URL = "https://ark.cn-beijing.volces.com/api/v3/responses"
MAX_TIMEOUT = 300
DEFAULT_TIMEOUT = 180

app = Flask(__name__)


@app.after_request
def after_request(resp):
    """统一跨域头：允许浏览器跨域调用代理（含直连方舟场景下代理转发的 Authorization 头）"""
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-API-Key"
    resp.headers["Access-Control-Max-Age"] = "86400"
    resp.headers["Access-Control-Allow-Credentials"] = "false"
    return resp


@app.route("/")
def index():
    """返回牛蛙收购单统计系统前端页面"""
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/<path:filename>")
def static_file(filename):
    """仅提供白名单内的静态资源"""
    if filename not in ALLOWED_STATIC:
        return jsonify({"error": "资源不存在"}), 404
    return send_from_directory(BASE_DIR, filename)


@app.route("/health")
def health():
    """健康检查"""
    return jsonify({"status": "ok"})


def _is_allowed_host(hostname):
    if not hostname:
        return False
    return any(hostname == suf or hostname.endswith("." + suf) for suf in ALLOWED_HOST_SUFFIXES)


def _extract_bearer(auth_header):
    """从 Authorization: Bearer xxx 中提取 token"""
    if not auth_header:
        return ""
    parts = auth_header.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return auth_header.strip()


@app.route("/api/doubao", methods=["POST", "OPTIONS"])
def doubao_proxy():
    """
    豆包视觉 API 代理。
    转发请求到火山引擎方舟 Responses API，避免前端 CORS 问题。
    支持三种鉴权传入方式：请求体 api_key / X-API-Key 头 / Authorization: Bearer 头。
    """
    if request.method == "OPTIONS":
        # 预检请求：CORS 响应头已由 after_request 统一附加
        return ("", 204)

    try:
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "请求体必须是 JSON 对象"}), 400

        # 从请求体 / 头中取出鉴权信息并移除，绝不转发给上游
        api_key = (
            body.pop("api_key", "")
            or request.headers.get("X-API-Key", "")
            or _extract_bearer(request.headers.get("Authorization", ""))
        ).strip()
        target_url = (body.pop("api_url", "") or DEFAULT_ARK_URL).strip()

        if not api_key:
            return jsonify({"error": "缺少 API Key"}), 400

        # SSRF 防护：仅允许白名单域名且必须为 https
        parsed = urlparse(target_url)
        if parsed.scheme != "https" or not _is_allowed_host(parsed.hostname):
            return jsonify({"error": "不支持的 API 地址（仅允许火山引擎方舟域名）"}), 400

        # 超时上限保护
        try:
            timeout = float(body.pop("_timeout", DEFAULT_TIMEOUT))
        except (TypeError, ValueError):
            timeout = DEFAULT_TIMEOUT
        timeout = max(1, min(timeout, MAX_TIMEOUT))

        req_data = json.dumps(body).encode("utf-8")
        proxy_req = Request(
            target_url,
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

        start_time = time.time()
        try:
            with urlopen(proxy_req, timeout=timeout) as resp:
                resp_body = resp.read().decode("utf-8", errors="replace")
                resp_data = json.loads(resp_body) if resp_body else {}
                resp_data["_proxy_time"] = round(time.time() - start_time, 2)
                return jsonify(resp_data)
        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            try:
                error_data = json.loads(error_body)
            except Exception:
                error_data = {"error": error_body}
            error_data["_proxy_status"] = e.code
            logger.warning("上游返回错误 %s: %s", e.code, error_body[:300])
            return jsonify(error_data), e.code
        except URLError as e:
            logger.error("连接豆包 API 失败: %s", e.reason)
            return jsonify({"error": f"连接豆包API失败: {e.reason}"}), 502
        except Exception as e:  # 上游读取 / 解码等意外
            logger.exception("转发请求异常")
            return jsonify({"error": f"请求异常: {e}"}), 500

    except Exception as e:
        logger.exception("代理服务异常")
        return jsonify({"error": f"代理服务异常: {e}"}), 500


if __name__ == "__main__":
    print("=" * 50)
    print("豆包视觉 API 代理服务（同源托管前端）")
    print("=" * 50)
    print(f"Python: {sys.version.split()[0]}")
    print("监听地址: http://0.0.0.0:5000")
    print("页面:    http://127.0.0.1:5000/")
    print("API 端点: POST /api/doubao - 豆包视觉API代理")
    print("         GET  /health     - 健康检查")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
