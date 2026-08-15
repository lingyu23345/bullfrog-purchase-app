// doubao-proxy-worker.js
// 豆包视觉 OCR 代理（Serverless，替代本地 paddle_server.py 的 /api/doubao）
// 部署方式：
//   1) Cloudflare Workers：
//      - 将本文件内容粘贴到 Worker 编辑器中，或
//      - 安装 wrangler 后执行 `wrangler deploy doubao-proxy-worker.js`
//      - 无需任何依赖，纯标准 Fetch API
//   2) Vercel 备选：见文件末尾注释（api/doubao.js）
//
// 环境变量（可选）：
//   WORKER_SECRET —— 若设置，调用方必须在请求头 X-Worker-Secret 或查询参数 ?secret= 中携带相同值，
//                    否则返回 403。建议公开部署时设置，避免被他人白嫖你的豆包额度。
//
// 前端配置：将「API 端点（代理）」填写为本 Worker 的地址，例如
//   https://bullfrog-proxy.<你的子域>.workers.dev/api/doubao

const DEFAULT_ARK_URL = "https://ark.cn-beijing.volces.com/api/v3/responses";
const ALLOWED_HOST_SUFFIXES = ["volces.com", "volcengineapi.com"];

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-API-Key, X-Worker-Secret",
    "Access-Control-Max-Age": "86400",
  };
}

function isAllowedHost(hostname) {
  if (!hostname) return false;
  return ALLOWED_HOST_SUFFIXES.some(s => hostname === s || hostname.endsWith("." + s));
}

function extractBearer(header) {
  if (!header) return "";
  const parts = header.split(/\s+/);
  if (parts.length === 2 && parts[0].toLowerCase() === "bearer") return parts[1].trim();
  return header.trim();
}

function json(payload, status, extraHeaders) {
  return new Response(JSON.stringify(payload), {
    status: status,
    headers: Object.assign({}, corsHeaders(), { "Content-Type": "application/json" }, extraHeaders || {}),
  });
}

export default {
  async fetch(request, env) {
    // 预检请求（CORS）
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders() });
    }

    if (request.method !== "POST") {
      return json({ error: "仅支持 POST" }, 405);
    }

    // 可选 Secret 校验（请求头或查询参数）
    const url = new URL(request.url);
    const secret = (env && env.WORKER_SECRET) || "";
    if (secret) {
      const provided = request.headers.get("X-Worker-Secret") || url.searchParams.get("secret") || "";
      if (provided !== secret) {
        return json({ error: "未授权：缺少/错误的 X-Worker-Secret" }, 403);
      }
    }

    // 解析请求体
    let body;
    try {
      body = await request.json();
    } catch (e) {
      return json({ error: "请求体必须是 JSON" }, 400);
    }
    if (typeof body !== "object" || body === null) {
      return json({ error: "请求体必须是 JSON 对象" }, 400);
    }

    // 从 请求体 / 请求头 取鉴权（绝不回传上游）
    const apiKey = (body.api_key || request.headers.get("X-API-Key") || extractBearer(request.headers.get("Authorization")) || "").toString().trim();
    const targetUrl = (body.api_url || DEFAULT_ARK_URL).toString().trim();

    if (!apiKey) {
      return json({ error: "缺少 API Key" }, 400);
    }

    // SSRF 防护：仅允许火山引擎方舟域名且必须为 https
    let parsed;
    try { parsed = new URL(targetUrl); } catch (e) {
      return json({ error: "无效的 API 地址" }, 400);
    }
    if (parsed.protocol !== "https:" || !isAllowedHost(parsed.hostname)) {
      return json({ error: "仅允许火山引擎方舟域名（volces.com / volcengineapi.com）" }, 400);
    }

    // 构造转发体：剔除代理专用字段
    const forward = Object.assign({}, body);
    delete forward.api_key;
    delete forward.api_url;
    delete forward._timeout;

    let upstreamResp;
    try {
      upstreamResp = await fetch(targetUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": "Bearer " + apiKey,
        },
        body: JSON.stringify(forward),
      });
    } catch (e) {
      return json({ error: "连接豆包 API 失败：" + e.message }, 502);
    }

    const respText = await upstreamResp.text();
    return new Response(respText, {
      status: upstreamResp.status,
      headers: corsHeaders(),
    });
  },
};

/*
=== Vercel 备选（api/doubao.js）===
// 在项目根创建 api/doubao.js，部署到 Vercel 后访问 https://<你的域名>/api/doubao
export default async function handler(req, res) {
  if (req.method === "OPTIONS") { res.status(204).end(); return; }
  if (req.method !== "POST") { res.status(405).json({ error: "仅支持 POST" }); return; }
  const secret = process.env.WORKER_SECRET || "";
  if (secret && req.headers["x-worker-secret"] !== secret && new URL(req.url, "http://x").searchParams.get("secret") !== secret) {
    res.status(403).json({ error: "未授权" }); return;
  }
  const body = req.body || {};
  const apiKey = body.api_key || req.headers["x-api-key"] || (req.headers["authorization"]||"").replace(/^Bearer\s+/i,"") || "";
  const targetUrl = body.api_url || "https://ark.cn-beijing.volces.com/api/v3/responses";
  if (!/^https:\/\/([\w-]+\.)*(volces\.com|volcengineapi\.com)([/:]|$)/.test(targetUrl)) {
    res.status(400).json({ error: "仅允许火山引擎方舟域名" }); return;
  }
  const forward = { ...body };
  delete forward.api_key; delete forward.api_url; delete forward._timeout;
  const r = await fetch(targetUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": "Bearer " + apiKey },
    body: JSON.stringify(forward),
  });
  const t = await r.text();
  res.status(r.status).setHeader("Access-Control-Allow-Origin","*").send(t);
}
*/
