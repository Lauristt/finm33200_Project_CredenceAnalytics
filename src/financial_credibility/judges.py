"""Semantic judge implementations.

Judges answer narrow questions that are hard to encode deterministically:
evidence support, source independence, reasoning quality, numeric fallback, and
logic verification. They never produce the final global score directly.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

from .config import ToolkitConfig
from .models import ArgumentType, Evidence, SupportLabel, VerificationCheck, VerificationVerdict, clamp
from .net import urlopen_request
from .sources import canonical_domain
from .text import token_overlap


class SemanticJudge(ABC):
    """Interface shared by local and LLM-backed judges."""

    @abstractmethod
    def judge_evidence_support(self, claim: str, evidence: Evidence) -> tuple[SupportLabel, float, list[str]]:
        """Judge whether one evidence item supports or contradicts the claim."""
        raise NotImplementedError

    @abstractmethod
    def judge_independence(self, first: Evidence, second: Evidence) -> tuple[float, list[str]]:
        """Judge whether two evidence items are likely independent."""
        raise NotImplementedError

    @abstractmethod
    def judge_reasoning_quality(self, claim: str, evidence: Evidence, argument_type: ArgumentType) -> tuple[float, list[str]]:
        """Judge whether an evidence item contains useful reasoning."""
        raise NotImplementedError

    @abstractmethod
    def judge_numeric_claim(self, claim: str, evidence: list[Evidence]) -> VerificationCheck:
        """Verify numeric claims when local fuzzy matching cannot decide."""
        raise NotImplementedError

    @abstractmethod
    def judge_logic_claim(
        self,
        claim: str,
        evidence: list[Evidence],
        argument_type: ArgumentType,
    ) -> VerificationCheck:
        """Verify the semantic logic or inference in a claim."""
        raise NotImplementedError


class HeuristicJudge(SemanticJudge):
    """No-key fallback judge based on token overlap and simple markers."""

    def judge_evidence_support(self, claim: str, evidence: Evidence) -> tuple[SupportLabel, float, list[str]]:
        combined = f"{evidence.title}\n{evidence.text}"
        overlap = token_overlap(claim, combined)
        notes = [f"token overlap={overlap:.2f}"]

        price_direction = _price_history_direction_support(claim, combined)
        if price_direction == "supports":
            return SupportLabel.SUPPORTS, 0.90, notes + ["price direction matched latest daily return"]
        if price_direction == "contradicts":
            return SupportLabel.CONTRADICTS, 0.82, notes + ["price direction contradicted latest daily return"]

        if _has_directional_contradiction(claim, combined):
            return SupportLabel.CONTRADICTS, 0.78, notes + ["directional contradiction marker"]

        numeric_bonus = max(0.0, evidence.numeric_consistency_score - 0.55)
        score = clamp(0.25 + overlap * 0.85 + numeric_bonus * 0.35)

        if score >= 0.68:
            return SupportLabel.SUPPORTS, round(score, 3), notes
        if score <= 0.34:
            return SupportLabel.NOT_ENOUGH_INFO, round(score, 3), notes + ["weak lexical support"]
        return SupportLabel.NOT_ENOUGH_INFO, round(score, 3), notes

    def judge_independence(self, first: Evidence, second: Evidence) -> tuple[float, list[str]]:
        if canonical_domain(first.url) == canonical_domain(second.url):
            return 0.25, ["same canonical domain"]
        title_overlap = token_overlap(first.title, second.title)
        if title_overlap > 0.80:
            return 0.40, [f"very similar titles overlap={title_overlap:.2f}"]
        return 0.85, ["different domains and title text"]

    def judge_reasoning_quality(self, claim: str, evidence: Evidence, argument_type: ArgumentType) -> tuple[float, list[str]]:
        text = f"{evidence.title}\n{evidence.text}".lower()
        if argument_type in {
            ArgumentType.METRIC_FACT,
            ArgumentType.EVENT_FACT,
            ArgumentType.ATTRIBUTION_FACT,
        }:
            return 0.55, ["reasoning quality is secondary for factual claim type"]

        markers = [
            r"\bbecause\b",
            r"\bdue to\b",
            r"\bassum",
            r"\bguidance\b",
            r"\bconsensus\b",
            r"\bmargin\b",
            r"\brevenue\b",
            r"\bcash flow\b",
            r"\bvaluation\b",
            r"\bmultiple\b",
            r"\brisk\b",
        ]
        hits = [pattern for pattern in markers if re.search(pattern, text)]
        score = clamp(0.30 + 0.07 * len(hits) + 0.15 * evidence.numeric_consistency_score)
        return round(score, 3), [f"reasoning markers={len(hits)}"]

    def judge_numeric_claim(self, claim: str, evidence: list[Evidence]) -> VerificationCheck:
        best = max((item.numeric_consistency_score for item in evidence), default=0.0)
        if best >= 0.70:
            verdict = VerificationVerdict.PARTIALLY_VERIFIED
            summary = "Numeric values are partially supported by available evidence."
        elif best >= 0.35:
            verdict = VerificationVerdict.NOT_FOUND
            summary = "The exact numeric value was not found, but related numeric evidence exists."
        else:
            verdict = VerificationVerdict.NOT_FOUND
            summary = "The numeric value was not found in available evidence."
        return VerificationCheck(
            check_type="numeric_check",
            verdict=verdict.value,
            confidence=round(clamp(best), 3),
            summary=summary,
            evidence_urls=[item.url for item in evidence[:3]],
            method="heuristic_llm_fallback",
        )

    def judge_logic_claim(
        self,
        claim: str,
        evidence: list[Evidence],
        argument_type: ArgumentType,
    ) -> VerificationCheck:
        support = max((item.support_score for item in evidence), default=0.0)
        reasoning = max((item.reasoning_quality_score for item in evidence), default=0.0)
        confidence = round(clamp(0.45 * support + 0.55 * reasoning), 3)
        verdict = (
            VerificationVerdict.SUPPORTED
            if confidence >= 0.70
            else VerificationVerdict.PARTIALLY_SUPPORTED
            if confidence >= 0.45
            else VerificationVerdict.WEAK
        )
        return VerificationCheck(
            check_type="logic_check",
            verdict=verdict.value,
            confidence=confidence,
            summary="Heuristic logic check based on evidence support and reasoning markers.",
            evidence_urls=[item.url for item in evidence[:3]],
            method="heuristic",
        )


class OpenAIJudge(HeuristicJudge):
    """OpenAI-backed JSON judge with heuristic fallback on any API/parse error."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 25.0,
        allow_insecure_ssl_fallback: bool = False,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.allow_insecure_ssl_fallback = allow_insecure_ssl_fallback

    def judge_evidence_support(self, claim: str, evidence: Evidence) -> tuple[SupportLabel, float, list[str]]:
        prompt = {
            "task": "evidence_support",
            "claim": claim,
            "evidence_title": evidence.title,
            "evidence_text": evidence.text[:4000],
            "allowed_labels": [label.value for label in SupportLabel],
            "instruction": "Return JSON with label, score_0_to_10, and one short reason.",
        }
        try:
            data = self._chat_json(prompt)
            label = SupportLabel(data.get("label", SupportLabel.NOT_ENOUGH_INFO.value))
            score = _support_score_from_llm_data(data, label)
            return label, score, [f"openai judge: {data.get('reason', '')}".strip()]
        except Exception as exc:
            label, score, notes = super().judge_evidence_support(claim, evidence)
            return label, score, notes + [f"openai fallback: {exc}"]

    def judge_numeric_claim(self, claim: str, evidence: list[Evidence]) -> VerificationCheck:
        prompt = _verification_prompt("numeric_verification", claim, evidence)
        try:
            data = self._chat_json(prompt)
            return _check_from_llm_data("numeric_check", data, evidence, "openai")
        except Exception as exc:
            check = super().judge_numeric_claim(claim, evidence)
            return _append_issue(check, f"openai fallback: {exc}")

    def judge_logic_claim(
        self,
        claim: str,
        evidence: list[Evidence],
        argument_type: ArgumentType,
    ) -> VerificationCheck:
        prompt = _verification_prompt(
            "logic_verification",
            claim,
            evidence,
            extra={"argument_type": argument_type.value},
        )
        try:
            data = self._chat_json(prompt)
            return _check_from_llm_data("logic_check", data, evidence, "openai")
        except Exception as exc:
            check = super().judge_logic_claim(claim, evidence, argument_type)
            return _append_issue(check, f"openai fallback: {exc}")

    def _chat_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Call OpenAI chat completions and parse a JSON object response."""
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a narrow financial evidence judge. Return only valid JSON.",
                },
                {"role": "user", "content": json.dumps(payload)},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen_request(
            request,
            timeout=self.timeout,
            allow_insecure_ssl_fallback=self.allow_insecure_ssl_fallback,
        ) as response:
            raw = json.loads(response.read().decode("utf-8"))
        content = raw["choices"][0]["message"]["content"]
        return _loads_json_object(content)


class AnthropicJudge(HeuristicJudge):
    """Anthropic-backed JSON judge with heuristic fallback on any API/parse error."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 25.0,
        allow_insecure_ssl_fallback: bool = False,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.allow_insecure_ssl_fallback = allow_insecure_ssl_fallback

    def judge_evidence_support(self, claim: str, evidence: Evidence) -> tuple[SupportLabel, float, list[str]]:
        prompt = {
            "task": "evidence_support",
            "claim": claim,
            "evidence_title": evidence.title,
            "evidence_text": evidence.text[:4000],
            "allowed_labels": [label.value for label in SupportLabel],
            "instruction": "Return JSON with label, score_0_to_10, and one short reason.",
        }
        try:
            data = self._messages_json(prompt)
            label = SupportLabel(data.get("label", SupportLabel.NOT_ENOUGH_INFO.value))
            score = _support_score_from_llm_data(data, label)
            return label, score, [f"anthropic judge: {data.get('reason', '')}".strip()]
        except Exception as exc:
            label, score, notes = super().judge_evidence_support(claim, evidence)
            return label, score, notes + [f"anthropic fallback: {exc}"]

    def judge_numeric_claim(self, claim: str, evidence: list[Evidence]) -> VerificationCheck:
        prompt = _verification_prompt("numeric_verification", claim, evidence)
        try:
            data = self._messages_json(prompt)
            return _check_from_llm_data("numeric_check", data, evidence, "anthropic")
        except Exception as exc:
            check = super().judge_numeric_claim(claim, evidence)
            return _append_issue(check, f"anthropic fallback: {exc}")

    def judge_logic_claim(
        self,
        claim: str,
        evidence: list[Evidence],
        argument_type: ArgumentType,
    ) -> VerificationCheck:
        prompt = _verification_prompt(
            "logic_verification",
            claim,
            evidence,
            extra={"argument_type": argument_type.value},
        )
        try:
            data = self._messages_json(prompt)
            return _check_from_llm_data("logic_check", data, evidence, "anthropic")
        except Exception as exc:
            check = super().judge_logic_claim(claim, evidence, argument_type)
            return _append_issue(check, f"anthropic fallback: {exc}")

    def _messages_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Call Anthropic messages and parse a JSON object response."""
        body = {
            "model": self.model,
            "max_tokens": 400,
            "temperature": 0,
            "system": "You are a narrow financial evidence judge. Return only valid JSON.",
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Return exactly one JSON object. Do not wrap it in markdown.\n\n"
                        + json.dumps(payload)
                    ),
                }
            ],
        }
        request = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen_request(
            request,
            timeout=self.timeout,
            allow_insecure_ssl_fallback=self.allow_insecure_ssl_fallback,
        ) as response:
            raw = json.loads(response.read().decode("utf-8"))
        content = "".join(block.get("text", "") for block in raw.get("content", []))
        return _loads_json_object(content)


def create_judge(config: ToolkitConfig) -> SemanticJudge:
    """Choose OpenAI, Anthropic, or heuristic judging from `ToolkitConfig`."""
    provider = config.llm_provider.lower()
    if provider in {"auto", "openai"} and config.openai_api_key and config.openai_model:
        return OpenAIJudge(
            config.openai_api_key,
            config.openai_model,
            config.request_timeout,
            config.allow_insecure_ssl_fallback,
        )
    if provider in {"auto", "anthropic"} and config.anthropic_api_key and config.anthropic_model:
        return AnthropicJudge(
            config.anthropic_api_key,
            config.anthropic_model,
            config.request_timeout,
            config.allow_insecure_ssl_fallback,
        )
    return HeuristicJudge()


def _verification_prompt(
    task: str,
    claim: str,
    evidence: list[Evidence],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the small JSON task sent to LLM-backed verification judges."""
    return {
        "task": task,
        "claim": claim,
        "evidence": [
            {
                "title": item.title,
                "url": item.url,
                "source_type": item.source_type.value,
                "text": item.text[:2000],
            }
            for item in evidence[:5]
        ],
        "allowed_verdicts": [verdict.value for verdict in VerificationVerdict],
        "instruction": (
            "Return JSON with verdict, confidence_0_to_1, summary, and issues. "
            "Do not convert forecasts, opinions, investment judgments, discussion questions, or vague market color "
            "into factual verdicts. Vague 'beat', 'priced in', and 'beating quarter after quarter' commentary is "
            "not fact-checkable unless a concrete metric, period, value, and comparison baseline are stated. "
            "For numeric_verification, check whether numbers/periods/units in the claim are supported. "
            "For logic_verification, check whether the reasoning or inference in the claim is supported."
        ),
        **(extra or {}),
    }


def _check_from_llm_data(
    check_type: str,
    data: dict[str, Any],
    evidence: list[Evidence],
    method: str,
) -> VerificationCheck:
    """Normalize raw LLM JSON into a `VerificationCheck`."""
    verdict = str(data.get("verdict", VerificationVerdict.INSUFFICIENT.value))
    allowed = {item.value for item in VerificationVerdict}
    if verdict not in allowed:
        verdict = VerificationVerdict.INSUFFICIENT.value
    confidence = clamp(float(data.get("confidence_0_to_1", data.get("confidence", 0.0))))
    issues = data.get("issues", [])
    if isinstance(issues, str):
        issues = [issues]
    return VerificationCheck(
        check_type=check_type,
        verdict=verdict,
        confidence=round(confidence, 3),
        summary=str(data.get("summary", "")),
        evidence_urls=[item.url for item in evidence[:5]],
        issues=[str(issue) for issue in issues],
        method=method,
    )


def _support_score_from_llm_data(data: dict[str, Any], label: SupportLabel) -> float:
    raw_score = data.get("score_0_to_10")
    if raw_score is not None:
        return clamp(float(raw_score) / 10.0)
    return {
        SupportLabel.SUPPORTS: 0.75,
        SupportLabel.CONTRADICTS: 0.75,
        SupportLabel.NOT_ENOUGH_INFO: 0.25,
    }[label]


def _loads_json_object(content: str) -> dict[str, Any]:
    """Parse a JSON object even if a model wraps it in markdown or prose."""
    text = content.strip()
    if not text:
        raise ValueError("empty JSON response")

    candidates = [text]
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if fence:
        candidates.insert(0, fence.group(1).strip())

    decoder = json.JSONDecoder()
    for candidate in candidates:
        candidate = candidate.strip()
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        for match in re.finditer(r"\{", candidate):
            try:
                parsed, _ = decoder.raw_decode(candidate[match.start() :])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed

    raise ValueError("could not parse JSON object from judge response")


def _append_issue(check: VerificationCheck, issue: str) -> VerificationCheck:
    """Return a copy of a check with one additional issue."""
    return VerificationCheck(
        check_type=check.check_type,
        verdict=check.verdict,
        confidence=check.confidence,
        summary=check.summary,
        evidence_urls=check.evidence_urls,
        issues=[*check.issues, issue],
        method=check.method,
    )


def _has_directional_contradiction(claim: str, evidence: str) -> bool:
    claim_lower = claim.lower()
    evidence_lower = evidence.lower()
    positive = r"\b(grew|growth|increased|rose|up|beat|expanded|higher)\b"
    negative = r"\b(declined|decreased|fell|down|missed|contracted|lower)\b"
    return (
        bool(re.search(positive, claim_lower) and re.search(negative, evidence_lower))
        or bool(re.search(negative, claim_lower) and re.search(positive, evidence_lower))
    )


def _price_history_direction_support(claim: str, evidence: str) -> str | None:
    evidence_lower = evidence.lower()
    if "latest_daily_return_pct" not in evidence_lower:
        return None
    match = re.search(r"latest_daily_return_pct\s+(-?\d+(?:\.\d+)?)%", evidence_lower)
    if not match:
        return None
    latest_return = float(match.group(1))
    claim_lower = claim.lower()
    negative_claim = bool(re.search(r"\b(fell|falls|dropped|declined|lost|slid|tumbled|plunged|down)\b", claim_lower))
    positive_claim = bool(re.search(r"\b(rose|rises|gained|jumped|surged|rallied|advanced|climbed|up)\b", claim_lower))
    if negative_claim and latest_return < 0:
        return "supports"
    if positive_claim and latest_return > 0:
        return "supports"
    if negative_claim and latest_return > 0:
        return "contradicts"
    if positive_claim and latest_return < 0:
        return "contradicts"
    return None
