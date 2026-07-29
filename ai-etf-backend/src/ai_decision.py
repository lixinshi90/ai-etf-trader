# -*- coding: utf-8 -*-
"""
AI 决策模块：调用大模型生成针对ETF的买/卖/持有决策（JSON格式）
- 使用环境变量 OPENAI_API_KEY（或 .env 配置）
- 可通过环境变量 MODEL_NAME 指定模型，默认 gpt-4o-mini
- 可通过环境变量 BASE_URL 支持 OpenAI 兼容服务（DeepSeek/Groq/Mistral/BigModel等）
- 可通过 TIMEOUT_SECONDS / MAX_RETRIES 配置超时与重试
- 可通过 FALLBACK_MODELS 配置回退模型（逗号分隔）
- 支持当日决策缓存：如果已存在同日决策文件则直接复用，减少反复计费与失败
- 将当日的 System Prompt 与 User Message 落盘保存，便于审计
- 将决策JSON落盘至 decisions 目录
"""
from __future__ import annotations

import glob
import json
import os
import re
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from dotenv import load_dotenv

from .prompts import SYSTEM_PROMPT, build_user_message, FEW_SHOTS

# 延迟导入以更好地给出错误提示
try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)


def _today_str() -> str:
    return datetime.now().strftime("%Y%m%d")


def _now_ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _safe_json_parse(text: str) -> Dict[str, Any]:
    """尽力从文本中解析出 JSON 对象（dict）。

    目标：显著降低 `Expecting ',' delimiter` 等解析失败率。

    支持：
    - ```json ...``` 代码块
    - 输出前后夹杂解释文字（从首个 { 到最后一个 } 截取）
    - 常见脏字符：BOM、中文引号

    注意：这里不做“语义修复”，只做轻量规则清洗；仍失败则抛错。
    """
    if not text or not str(text).strip():
        raise ValueError("空响应，无法解析JSON")

    raw = str(text).strip().lstrip("\ufeff")

    # 1) 优先提取 markdown json 代码块
    m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", raw, flags=re.IGNORECASE)
    if m:
        candidate = m.group(1).strip()
    else:
        candidate = raw

    # 2) 若不是以 { 开头，尝试截取第一个 { 到最后一个 }
    s = candidate.strip()
    if not s.startswith("{"):
        l = s.find("{")
        r = s.rfind("}")
        if l != -1 and r != -1 and r > l:
            s = s[l : r + 1]

    # 3) 清洗常见问题：中文引号
    s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")

    # 4) 解析
    obj = json.loads(s)
    if not isinstance(obj, dict):
        raise ValueError("解析结果不是对象")
    return obj


def _find_cached_decision(decisions_dir: str, etf_code: str, date_str: Optional[str] = None) -> Optional[Tuple[str, Dict[str, Any]]]:
    """查找当日该标的已有决策文件，返回 (文件路径, 决策对象) 或 None。"""
    if date_str is None:
        date_str = _today_str()
    pattern = os.path.join(decisions_dir, f"{date_str}_{etf_code}_*.json")
    files = sorted(glob.glob(pattern), reverse=True)
    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                obj = json.load(f)
            if isinstance(obj, dict) and obj.get("decision"):
                return fp, obj
        except Exception:
            continue
    return None


def get_ai_decision(
    etf_code: str,
    df,
    prompts_dir: Optional[str] = None,
    decisions_dir: Optional[str] = None,
    system_prompt: str = SYSTEM_PROMPT,
    model_name: Optional[str] = None,
    use_cache: bool = True,
    force_date: Optional[datetime.date] = None,
) -> Dict[str, Any]:
    """获取AI决策（返回字典，包含 decision/ confidence/ reasoning/ target_price/ stop_loss/ take_profit）
    - 会将 Prompt 和 决策JSON 落盘
    - 默认优先使用当日缓存
    """
    # 环境与目录
    load_dotenv(override=True)  # 优先以 .env 覆盖外部环境，避免混配
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("未设置 OPENAI_API_KEY 环境变量，请在 .env 中配置或导出环境变量")

    if model_name is None:
        model_name = os.getenv("MODEL_NAME", "gpt-4o-mini")

    base_url = os.getenv("BASE_URL")  # 例如 DeepSeek/Groq/BigModel 兼容端点
    try:
        timeout_s = float(os.getenv("TIMEOUT_SECONDS", "120"))  # 默认120秒
    except Exception:
        timeout_s = 120.0
    try:
        max_retries = int(os.getenv("MAX_RETRIES", "3"))  # 默认3次，满足“最多重试3次”
    except Exception:
        max_retries = 3

    fallback_models_env = os.getenv("FALLBACK_MODELS", "gpt-4o")
    fallback_models = [m.strip() for m in fallback_models_env.split(",") if m.strip()]

    if prompts_dir is None:
        prompts_dir = os.path.join(_project_root(), "prompts")
    if decisions_dir is None:
        decisions_dir = os.path.join(_project_root(), "decisions")
    _ensure_dir(prompts_dir)
    _ensure_dir(decisions_dir)

    date_str = force_date.strftime("%Y%m%d") if force_date else _today_str()

    # 当日缓存命中则直接返回（优先复用，避免重复计费/失败）
    if use_cache:
        cached = _find_cached_decision(decisions_dir, etf_code, date_str=date_str)
        if cached:
            _, cached_obj = cached
            return cached_obj

        # 进一步：如果当天已有 raw 输出但决策 json 没落盘，可在此扩展“从 raw 重建”。
        # 目前先不自动重建，避免误解析；但 raw 已会写入 logs/llm_raw_* 便于手工排查。

    # 构建消息
    user_message = build_user_message(etf_code, df)
    use_few = os.getenv("FEW_SHOT_ENABLED", "false").lower() == "true"
    messages = [{"role": "system", "content": system_prompt}]
    if use_few:
        messages += FEW_SHOTS
    messages.append({"role": "user", "content": user_message})

    # 客户端
    if OpenAI is None:  # pragma: no cover
        raise RuntimeError("openai 库不可用，请 pip install openai")

    client_kwargs = {"api_key": api_key, "timeout": timeout_s, "max_retries": max_retries}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = OpenAI(**client_kwargs)

    # BigModel（open.bigmodel.cn）等有些端点可能不支持 JSON Mode，这里做兼容：
    use_json_mode = True
    if base_url and ("open.bigmodel.cn" in base_url.lower()):
        use_json_mode = False

    # 组织候选模型：主模型 + 回退模型
    tried_models = []
    model_candidates = [model_name] + [m for m in fallback_models if m not in tried_models]

    import time as _time

    last_err: Optional[Exception] = None
    decision: Optional[Dict[str, Any]] = None

    for m in model_candidates:
        tried_models.append(m)
        for attempt in range(1, max_retries + 1):
            try:
                print(f"调用模型 {m}（第{attempt}次尝试）...")
                kwargs = dict(
                    model=m,
                    messages=messages,
                    temperature=0.3,
                    timeout=timeout_s,
                )
                if use_json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                resp = client.chat.completions.create(**kwargs)
                raw_text = resp.choices[0].message.content if resp and resp.choices else ""

                # 记录原始输出（成功/失败都可能需要排查），避免“看不到模型到底回了什么”
                logs_dir = os.path.join(_project_root(), "logs")
                _ensure_dir(logs_dir)
                raw_fp = os.path.join(logs_dir, f"llm_raw_{date_str}_{etf_code}_{_now_ts()}_{m}.txt")
                try:
                    with open(raw_fp, "w", encoding="utf-8") as f:
                        f.write(raw_text or "")
                except Exception:
                    pass

                decision = _safe_json_parse(raw_text)
                print(f"模型 {m} 调用成功！")
                break
            except Exception as e:
                last_err = e
                if attempt < max_retries:
                    wait = 5 * (2 ** (attempt - 1))
                    print(f"❌ 模型{m}调用失败（第{attempt}次）：{e}")
                    print(f"⏳ {wait}秒后重试...")
                    _time.sleep(wait)
                else:
                    print(f"❌ 模型{m}调用失败且达到最大重试次数：{e}")
                    if m != model_candidates[-1]:
                        print(f"📌 尝试回退模型...")
        if decision is not None:
            model_name = m
            break

    if decision is None:
        # 全部尝试失败
        raise RuntimeError(f"模型调用失败（已尝试：{model_candidates}）：{last_err}")

    # 基础字段兜底
    decision.setdefault("decision", "hold")
    decision.setdefault("confidence", 0.5)
    decision.setdefault("reasoning", "模型未提供详细理由")
    for k in ("target_price", "stop_loss", "take_profit"):
        decision.setdefault(k, None)

    # 落盘
    date_str = _today_str()
    ts = _now_ts()
    prompt_file = os.path.join(prompts_dir, f"{date_str}_{etf_code}_{ts}_prompt.txt")
    decision_file = os.path.join(decisions_dir, f"{date_str}_{etf_code}_{ts}.json")

    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write("System Prompt:\n" + system_prompt + "\n\n")
        f.write("User Message:\n" + user_message + "\n")

    with open(decision_file, "w", encoding="utf-8") as f:
        json.dump(decision, f, ensure_ascii=False, indent=2)

    return decision
