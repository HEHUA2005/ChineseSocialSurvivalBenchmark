"""轻量 OpenAI 兼容 API 客户端（基于 requests，无外部依赖）。"""
import json
import time
import requests

import config.settings as settings


class LLMClient:
    def __init__(self, model=None, base_url=None, api_key=None, temperature=None, max_tokens=None):
        self.base_url = base_url or settings.API_BASE
        self.api_key = api_key or settings.require_api_key()
        self.model = model or settings.GENERATION_MODEL
        self.temperature = settings.TEMPERATURE if temperature is None else temperature
        self.max_tokens = settings.MAX_TOKENS if max_tokens is None else max_tokens
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def chat(self, messages, temperature=None, max_tokens=None, json_mode=False, model=None, retries=None):
        """发送 chat 请求，返回文本内容。带重试和指数退避。

        针对 reasoning 模型（如 deepseek-v4-flash-free）：若模型把全部 token
        预算消耗在推理上导致 content 为空，则自动翻倍 max_tokens 重试。
        """
        mt = self.max_tokens if max_tokens is None else max_tokens
        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": mt,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        retries = settings.MAX_RETRIES if retries is None else retries
        last_err = None
        for attempt in range(retries):
            try:
                resp = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=payload,
                    timeout=settings.TIMEOUT,
                )
                if resp.status_code != 200:
                    last_err = f"HTTP {resp.status_code}: {resp.text[:300]}"
                else:
                    data = resp.json()
                    msg = data["choices"][0]["message"]
                    content = msg.get("content") or ""
                    reasoning = msg.get("reasoning_content") or ""
                    if not content.strip():
                        if reasoning.strip() and mt < 65536:
                            # 推理吃光预算 → 翻倍重试
                            mt = mt * 2
                            payload["max_tokens"] = mt
                            last_err = f"推理耗尽预算(content空, 翻倍至{mt}重试)"
                            continue
                        last_err = f"空响应（content与reasoning均无内容）"
                        raise RuntimeError(last_err)
                    return content.strip()
            except Exception as e:
                last_err = str(e)
            time.sleep(min(2 ** attempt, 20))
        raise RuntimeError(f"LLM 请求失败 ({self.model}): {last_err}")

    def chat_json(self, messages, temperature=None, max_tokens=None):
        """发送请求并解析 JSON 输出。优先 json_mode，失败自动降级为非 json_mode 并宽容解析。"""
        # 尝试 json_mode
        try:
            raw = self.chat(messages, temperature=temperature, max_tokens=max_tokens, json_mode=True)
            if raw and raw.strip():
                return parse_json(raw)
        except Exception:
            pass
        # 降级：普通模式重试，解析时更宽容
        raw = self.chat(messages, temperature=temperature, max_tokens=max_tokens, json_mode=False)
        return parse_json(raw)


def parse_json(raw: str) -> dict:
    """从 LLM 输出中稳健地解析 JSON（容忍 markdown fence / 前后废话）。"""
    raw = raw.strip()
    if raw.startswith("```"):
        # 去掉 fence
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines)
    # 找到第一个 { 和最后一个 }
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        raw = raw[start:end + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 最后手段：把整段当纯文本，尝试逐行找 json 对象边界
        for line in raw.splitlines():
            s, e = line.find("{"), line.rfind("}")
            if s != -1 and e != -1 and e > s:
                try:
                    return json.loads(line[s:e + 1])
                except json.JSONDecodeError:
                    continue
        raise ValueError(f"无法解析 JSON: {raw[:500]}")