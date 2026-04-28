from __future__ import annotations

import json
from typing import Iterator, Optional
from urllib import error, request


class LlmClientError(RuntimeError):
    pass


def _label_or_default(value: Optional[str], mapping: dict[str, str]) -> str:
    if not value:
        return "未填写"
    return mapping.get(value, value)


def _format_score_context(score_context: Optional[dict]) -> str:
    if not score_context:
        return "当前尚未填写结构化评分，请结合问题和答案自行判断。"

    lines = [
        f"正确性：{_label_or_default(score_context.get('correctness_rating'), {'good': '好', 'medium': '一般', 'bad': '差'})}",
        f"完整性：{_label_or_default(score_context.get('completeness_rating'), {'full': '完整', 'partial': '部分缺失', 'missing': '明显缺失'})}",
        f"相关性：{_label_or_default(score_context.get('relevance_rating'), {'relevant': '相关', 'partial': '部分偏题', 'offtopic': '偏题'})}",
        f"表达清晰度：{_label_or_default(score_context.get('clarity_rating'), {'clear': '清晰', 'normal': '一般', 'unclear': '不清晰'})}",
        f"风险标记：{_label_or_default(score_context.get('risk_flag'), {'none': '无风险', 'factual': '事实风险', 'compliance': '合规风险', 'hallucination': '幻觉风险'})}",
        f"总体结论：{_label_or_default(score_context.get('overall_decision'), {'pass': '通过', 'rewrite': '待改写', 'fail': '不通过'})}",
    ]
    if (
        score_context.get("reasoning_completeness")
        or score_context.get("reasoning_consistency")
        or score_context.get("reasoning_support")
    ):
        lines.extend(
            [
                f"推理链完整性：{_label_or_default(score_context.get('reasoning_completeness'), {'strong': '强', 'medium': '一般', 'weak': '弱'})}",
                f"推理链自洽性：{_label_or_default(score_context.get('reasoning_consistency'), {'strong': '强', 'medium': '一般', 'weak': '弱'})}",
                f"结论与推理一致性：{_label_or_default(score_context.get('reasoning_support'), {'strong': '强', 'medium': '一般', 'weak': '弱'})}",
            ]
        )
    quick_comment_codes = score_context.get("quick_comment_codes") or []
    if isinstance(quick_comment_codes, list) and quick_comment_codes:
        lines.append(f"快速原因标签：{'、'.join(str(item) for item in quick_comment_codes if item)}")
    return "\n".join(lines)


def build_task_messages(
    *,
    action: str,
    question_text: str,
    context_text: Optional[str],
    answer_text: str,
    technical_type_code: Optional[str],
    score_context: Optional[dict],
    conversation_history: list[dict[str, str]],
    system_prompt: Optional[str],
) -> list[dict[str, str]]:
    default_system_prompt = (
        "你是 QA 评测平台里的专家辅助模型。"
        "你的输出必须服务于专家打分、风险判断和标准答案改写。"
        "你必须始终返回合法 JSON，不要输出 Markdown，不要输出代码块。"
        "JSON 字段固定为：evaluation_summary, decision_suggestion, strengths, problems, risk_notes, revised_answer, revised_answer_explanation。"
        "其中 strengths/problems/risk_notes 必须是字符串数组；decision_suggestion 只能是 pass、rewrite、fail 之一；revised_answer 必须给出一条可直接采纳的中文答案。"
        "无论专家追问多少轮，都要基于当前给定答案继续评估和改写，不要回退到旧答案版本。"
        "最终响应必须是单个 JSON 对象，不能附加任何额外说明。"
    )
    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": (system_prompt or default_system_prompt).strip(),
        }
    ]

    if action == "rewrite":
        task_instruction = "请重点判断当前答案哪里不合适，并给出更适合作为标准答案候选的修正版答案。"
    elif action == "risk_check":
        task_instruction = "请重点识别当前答案的事实风险、合规风险或幻觉风险，并在修正版中主动规避这些风险。"
    elif action == "fact_check":
        task_instruction = "请重点核查当前答案的事实可靠性、关键遗漏点和可疑表述，并据此给出更可靠的修正版。"
    else:
        task_instruction = "请从评测角度分析当前答案质量，并输出一条更适合作为标准答案候选的修正版答案。"

    content = [
        task_instruction,
        f"问题：{question_text}",
        f"当前答案：{answer_text}",
        f"QA 类型：{technical_type_code or '未指定'}",
    ]
    if context_text:
        content.append(f"背景信息：{context_text}")
    content.append("当前结构化评分：")
    content.append(_format_score_context(score_context))
    content.append(
        "请综合问题、当前答案、评分结果与后续专家意见，先评价当前答案是否合适，再给出一条你修正后的标准答案候选。"
    )
    content.append(
        "如果专家在后续对话里指出答案哪里还不好，你需要针对这些意见继续修正当前答案，并给出新的完整候选答案。"
    )
    if technical_type_code == "cot_qa":
        content.append("这是 CoT 题，请额外关注推理链是否完整、自洽、结论是否被前文支撑。")
    content.append(
        "请严格按以下 JSON 结构返回："
        '{"evaluation_summary":"...","decision_suggestion":"rewrite","strengths":["..."],'
        '"problems":["..."],"risk_notes":["..."],"revised_answer":"...",'
        '"revised_answer_explanation":"..."}'
    )

    messages.append({"role": "user", "content": "\n".join(content)})
    for message in conversation_history:
        role = message.get("role")
        content = message.get("content")
        if role != "user" or not isinstance(content, str) or not content.strip():
            continue
        messages.append({"role": "user", "content": content.strip()})
    return messages


def build_auto_review_messages(
    *,
    question_text: str,
    context_text: Optional[str],
    answer_text: str,
    technical_type_code: Optional[str],
    expert_profile_prompt: Optional[str],
    system_prompt: Optional[str],
) -> list[dict[str, str]]:
    default_system_prompt = (
        "你是 QA 评测平台里的自动化评测模型。"
        "你的任务是直接完成结构化评分，并给出一条更适合作为标准答案候选的修正版答案。"
        "你必须始终返回合法 JSON，不要输出 Markdown，不要输出代码块，不要补充额外说明。"
    )
    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": (system_prompt or default_system_prompt).strip(),
        }
    ]

    prompt_lines = [
        "请基于下面的 QA 内容，直接完成自动化评测。",
        f"问题：{question_text}",
        f"当前答案：{answer_text}",
        f"QA 类型：{technical_type_code or '未指定'}",
    ]
    if context_text:
        prompt_lines.append(f"背景信息：{context_text}")
    if expert_profile_prompt and expert_profile_prompt.strip():
        prompt_lines.append(f"专家个人说明：{expert_profile_prompt.strip()}")
    if technical_type_code == "cot_qa":
        prompt_lines.append("这是 CoT 题，请额外评估推理链完整性、自洽性和结论支撑情况。")

    prompt_lines.append(
        "请返回 JSON，字段固定为："
        "evaluation_summary, correctness_rating, completeness_rating, relevance_rating, "
        "clarity_rating, risk_flag, overall_decision, quick_comment_codes, "
        "reasoning_completeness, reasoning_consistency, reasoning_support, "
        "revised_answer, revised_answer_explanation。"
    )
    prompt_lines.append(
        "取值要求：correctness_rating 只能是 good|medium|bad；"
        "completeness_rating 只能是 full|partial|missing；"
        "relevance_rating 只能是 relevant|partial|offtopic；"
        "clarity_rating 只能是 clear|normal|unclear；"
        "risk_flag 只能是 none|factual|compliance|hallucination；"
        "overall_decision 只能是 pass|rewrite|fail；"
        "quick_comment_codes 是字符串数组，只能从以下选项里选择："
        "事实错误、遗漏关键点、表达不清、偏题、存在风险、答案较优；"
        "reasoning_completeness/reasoning_consistency/reasoning_support 只能是 strong|medium|weak 或 null。"
    )
    prompt_lines.append("revised_answer 必须给出一条可直接采用的中文标准答案候选。")
    prompt_lines.append(
        '{"evaluation_summary":"...",'
        '"correctness_rating":"good",'
        '"completeness_rating":"full",'
        '"relevance_rating":"relevant",'
        '"clarity_rating":"clear",'
        '"risk_flag":"none",'
        '"overall_decision":"rewrite",'
        '"quick_comment_codes":["遗漏关键点"],'
        '"reasoning_completeness":null,'
        '"reasoning_consistency":null,'
        '"reasoning_support":null,'
        '"revised_answer":"...",'
        '"revised_answer_explanation":"..."}'
    )
    messages.append({"role": "user", "content": "\n".join(prompt_lines)})
    return messages


def _extract_json_text(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end >= start:
        return stripped[start : end + 1]
    return stripped


def parse_review_response(value: str) -> dict:
    parsed: dict = {}
    try:
        raw = json.loads(_extract_json_text(value))
        if isinstance(raw, dict):
            parsed = raw
    except json.JSONDecodeError:
        parsed = {}

    evaluation_block = parsed.get("评价")
    if not isinstance(evaluation_block, dict):
        evaluation_block = {}

    def normalize_list(field_name: str) -> list[str]:
        raw_value = parsed.get(field_name)
        if isinstance(raw_value, list):
            return [str(item).strip() for item in raw_value if str(item).strip()]
        return []

    decision_raw = (
        parsed.get("decision_suggestion")
        or parsed.get("总体结论")
        or evaluation_block.get("总体结论")
        or "rewrite"
    )
    decision_map = {
        "pass": "pass",
        "通过": "pass",
        "rewrite": "rewrite",
        "待改写": "rewrite",
        "需要改写": "rewrite",
        "fail": "fail",
        "不通过": "fail",
    }
    decision = decision_map.get(str(decision_raw).strip().lower(), None)
    if decision is None:
        decision = decision_map.get(str(decision_raw).strip(), "rewrite")

    strengths = normalize_list("strengths")
    problems = normalize_list("problems")
    risk_notes = normalize_list("risk_notes")
    if not strengths and parsed.get("优点"):
        strengths = [str(parsed["优点"]).strip()]
    if not problems and evaluation_block:
        for key in ("正确性", "完整性", "相关性", "表达清晰度"):
            value_text = str(evaluation_block.get(key) or "").strip()
            if value_text:
                problems.append(f"{key}：{value_text}")
    risk_label = str(parsed.get("风险标记") or evaluation_block.get("风险标记") or "").strip()
    if not risk_notes and risk_label and risk_label not in {"无风险", "none"}:
        risk_notes = [risk_label]

    revised_answer = str(
        parsed.get("revised_answer")
        or parsed.get("修正后的标准答案候选")
        or parsed.get("建议答案")
        or ""
    ).strip()
    summary_parts = []
    if evaluation_block:
        for key in ("正确性", "完整性", "相关性", "表达清晰度"):
            value_text = str(evaluation_block.get(key) or "").strip()
            if value_text:
                summary_parts.append(f"{key}：{value_text}")
    evaluation_summary = str(
        parsed.get("evaluation_summary")
        or parsed.get("评价摘要")
        or ("\n".join(summary_parts) if summary_parts else value)
    ).strip()
    return {
        "evaluation_summary": evaluation_summary,
        "decision_suggestion": decision,
        "strengths": strengths,
        "problems": problems,
        "risk_notes": risk_notes,
        "revised_answer": revised_answer,
        "revised_answer_explanation": str(
            parsed.get("revised_answer_explanation")
            or parsed.get("修正说明")
            or ""
        ).strip(),
    }


def _normalize_enum(value: object, mapping: dict[str, str], default: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return default
    if raw in mapping:
        return mapping[raw]
    lowered = raw.lower()
    if lowered in mapping:
        return mapping[lowered]
    return default


def _normalize_quick_comments(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    allowed = {"事实错误", "遗漏关键点", "表达不清", "偏题", "存在风险", "答案较优"}
    alias = {
        "错误": "事实错误",
        "事实问题": "事实错误",
        "遗漏": "遗漏关键点",
        "缺少关键点": "遗漏关键点",
        "不清晰": "表达不清",
        "表达一般": "表达不清",
        "偏离问题": "偏题",
        "有风险": "存在风险",
        "较优": "答案较优",
    }
    normalized: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if not text:
            continue
        mapped = alias.get(text, text)
        if mapped in allowed and mapped not in normalized:
            normalized.append(mapped)
    return normalized


def parse_auto_review_response(value: str) -> dict:
    parsed: dict = {}
    try:
        raw = json.loads(_extract_json_text(value))
        if isinstance(raw, dict):
            parsed = raw
    except json.JSONDecodeError:
        parsed = {}

    structured = parsed.get("structured_score")
    if not isinstance(structured, dict):
        structured = {}
    evaluation = parsed.get("evaluation")
    if not isinstance(evaluation, dict):
        evaluation = {}

    correctness_map = {
        "good": "good",
        "好": "good",
        "良好": "good",
        "较好": "good",
        "medium": "medium",
        "一般": "medium",
        "中等": "medium",
        "bad": "bad",
        "差": "bad",
        "较差": "bad",
        "错误": "bad",
    }
    completeness_map = {
        "full": "full",
        "完整": "full",
        "partial": "partial",
        "部分缺失": "partial",
        "部分": "partial",
        "missing": "missing",
        "明显缺失": "missing",
        "缺失": "missing",
    }
    relevance_map = {
        "relevant": "relevant",
        "相关": "relevant",
        "高度相关": "relevant",
        "partial": "partial",
        "部分偏题": "partial",
        "部分相关": "partial",
        "offtopic": "offtopic",
        "偏题": "offtopic",
        "不相关": "offtopic",
    }
    clarity_map = {
        "clear": "clear",
        "清晰": "clear",
        "normal": "normal",
        "一般": "normal",
        "普通": "normal",
        "unclear": "unclear",
        "不清晰": "unclear",
        "模糊": "unclear",
    }
    risk_map = {
        "none": "none",
        "无风险": "none",
        "factual": "factual",
        "事实风险": "factual",
        "compliance": "compliance",
        "合规风险": "compliance",
        "hallucination": "hallucination",
        "幻觉风险": "hallucination",
    }
    decision_map = {
        "pass": "pass",
        "通过": "pass",
        "合格": "pass",
        "rewrite": "rewrite",
        "待改写": "rewrite",
        "需要改写": "rewrite",
        "fail": "fail",
        "不通过": "fail",
    }
    reasoning_map = {
        "strong": "strong",
        "强": "strong",
        "medium": "medium",
        "一般": "medium",
        "weak": "weak",
        "弱": "weak",
    }

    quick_comment_codes = _normalize_quick_comments(
        parsed.get("quick_comment_codes")
        or structured.get("quick_comment_codes")
        or evaluation.get("quick_reason_tag")
        or []
    )
    if isinstance(evaluation.get("quick_reason_tag"), str) and not quick_comment_codes:
        quick_comment_codes = _normalize_quick_comments([evaluation.get("quick_reason_tag")])

    return {
        "evaluation_summary": str(
            parsed.get("evaluation_summary")
            or parsed.get("evaluation")
            or parsed.get("评价摘要")
            or ""
        ).strip(),
        "correctness_rating": _normalize_enum(
            parsed.get("correctness_rating")
            or structured.get("correctness")
            or structured.get("correctness_rating")
            or evaluation.get("correctness"),
            correctness_map,
            "medium",
        ),
        "completeness_rating": _normalize_enum(
            parsed.get("completeness_rating")
            or structured.get("completeness")
            or structured.get("completeness_rating")
            or evaluation.get("completeness"),
            completeness_map,
            "partial",
        ),
        "relevance_rating": _normalize_enum(
            parsed.get("relevance_rating")
            or structured.get("relevance")
            or structured.get("relevance_rating")
            or evaluation.get("relevance"),
            relevance_map,
            "relevant",
        ),
        "clarity_rating": _normalize_enum(
            parsed.get("clarity_rating")
            or structured.get("clarity_of_expression")
            or structured.get("clarity")
            or evaluation.get("clarity"),
            clarity_map,
            "normal",
        ),
        "risk_flag": _normalize_enum(
            parsed.get("risk_flag")
            or structured.get("risk_flag")
            or evaluation.get("risk_flag"),
            risk_map,
            "none",
        ),
        "overall_decision": _normalize_enum(
            parsed.get("overall_decision")
            or structured.get("overall_conclusion")
            or structured.get("overall_decision")
            or evaluation.get("overall_conclusion"),
            decision_map,
            "rewrite",
        ),
        "quick_comment_codes": quick_comment_codes,
        "reasoning_completeness": _normalize_enum(
            parsed.get("reasoning_completeness"),
            reasoning_map,
            "",
        ),
        "reasoning_consistency": _normalize_enum(
            parsed.get("reasoning_consistency"),
            reasoning_map,
            "",
        ),
        "reasoning_support": _normalize_enum(
            parsed.get("reasoning_support"),
            reasoning_map,
            "",
        ),
        "revised_answer": str(
            parsed.get("revised_answer")
            or parsed.get("修正后的标准答案候选")
            or ""
        ).strip(),
        "revised_answer_explanation": str(
            parsed.get("revised_answer_explanation")
            or parsed.get("修正说明")
            or ""
        ).strip(),
    }


def format_auto_review_message(review: dict, candidate_answer_id: Optional[int]) -> str:
    lines = [
        "自动化评测结果",
        "",
        "结构化评分：",
        f"- 正确性：{review['correctness_rating']}",
        f"- 完整性：{review['completeness_rating']}",
        f"- 相关性：{review['relevance_rating']}",
        f"- 表达清晰度：{review['clarity_rating']}",
        f"- 风险标记：{review['risk_flag']}",
        f"- 总体结论：{review['overall_decision']}",
    ]
    if review.get("reasoning_completeness"):
        lines.extend(
            [
                f"- 推理链完整性：{review['reasoning_completeness']}",
                f"- 推理链自洽性：{review['reasoning_consistency']}",
                f"- 结论与推理一致性：{review['reasoning_support']}",
            ]
        )
    if review["quick_comment_codes"]:
        lines.append(f"- 快速原因标签：{'、'.join(review['quick_comment_codes'])}")
    if review["evaluation_summary"]:
        lines.extend(["", "评测摘要：", review["evaluation_summary"]])
    lines.extend(["", "建议答案：", review["revised_answer"] or "未生成新答案。"])
    if review["revised_answer_explanation"]:
        lines.extend(["", "修正说明：", review["revised_answer_explanation"]])
    if candidate_answer_id is not None:
        lines.extend(["", f"系统已生成候选答案 #{candidate_answer_id}。"])
    return "\n".join(lines)


def format_review_message(review: dict, candidate_answer_id: Optional[int]) -> str:
    lines = [
        "LLM 评估结果",
        f"建议结论：{review['decision_suggestion']}",
        "",
        "评价摘要：",
        review["evaluation_summary"] or "未返回摘要。",
    ]
    if review["strengths"]:
        lines.extend(["", "优点："])
        lines.extend(f"- {item}" for item in review["strengths"])
    if review["problems"]:
        lines.extend(["", "主要问题："])
        lines.extend(f"- {item}" for item in review["problems"])
    if review["risk_notes"]:
        lines.extend(["", "风险提示："])
        lines.extend(f"- {item}" for item in review["risk_notes"])
    lines.extend(["", "建议修正版答案：", review["revised_answer"] or "未生成新的修正版答案。"])
    if review["revised_answer_explanation"]:
        lines.extend(["", "修正说明：", review["revised_answer_explanation"]])
    if candidate_answer_id is not None:
        lines.extend(["", f"系统已生成候选答案 #{candidate_answer_id}，可以在右侧直接选用。"])
    return "\n".join(lines)


def call_openai_compatible_chat(
    *,
    base_url: str,
    api_key: str,
    model_name: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int = 800,
    top_p: float = 0.95,
) -> str:
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = json.dumps(
        {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
        }
    ).encode("utf-8")
    http_request = request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with request.urlopen(http_request, timeout=90) as response:
            response_text = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise LlmClientError(f"llm http error {exc.code}: {detail or exc.reason}") from exc
    except error.URLError as exc:
        raise LlmClientError(f"llm request failed: {exc.reason}") from exc

    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise LlmClientError("llm returned invalid json") from exc

    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()

    raise LlmClientError("llm returned empty content")


def iter_openai_compatible_chat(
    *,
    base_url: str,
    api_key: str,
    model_name: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int = 800,
    top_p: float = 0.95,
) -> Iterator[str]:
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = json.dumps(
        {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "stream": True,
        }
    ).encode("utf-8")
    http_request = request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with request.urlopen(http_request, timeout=180) as response:
            received_any = False
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="ignore").strip()
                if not line or not line.startswith("data:"):
                    continue
                data_text = line[5:].strip()
                if data_text == "[DONE]":
                    break
                try:
                    payload_json = json.loads(data_text)
                except json.JSONDecodeError:
                    continue
                choices = payload_json.get("choices")
                if not isinstance(choices, list) or not choices:
                    continue
                delta = choices[0].get("delta", {})
                content = delta.get("content") if isinstance(delta, dict) else None
                if isinstance(content, str) and content:
                    received_any = True
                    yield content
            if not received_any:
                raise LlmClientError("llm returned empty content")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise LlmClientError(f"llm http error {exc.code}: {detail or exc.reason}") from exc
    except error.URLError as exc:
        raise LlmClientError(f"llm request failed: {exc.reason}") from exc
