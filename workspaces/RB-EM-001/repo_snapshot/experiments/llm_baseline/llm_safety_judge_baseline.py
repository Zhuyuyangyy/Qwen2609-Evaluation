"""
LLM Safety Judge Baseline

Uses an LLM as a zero-shot safety judge to classify agent action requests
into one of four categories: AUTO_EXECUTE, SIMULATE_FIRST, HUMAN_REVIEW, BLOCK.
"""

import json
import os
import re
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class SafetyDecision(Enum):
    AUTO_EXECUTE = "AUTO_EXECUTE"
    SIMULATE_FIRST = "SIMULATE_FIRST"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    BLOCK = "BLOCK"


@dataclass
class LLMJudgeResult:
    sample_id: str
    decision: str
    rationale: str
    raw_output: str
    parse_success: bool
    retry_count: int = 0
    error: Optional[str] = None


class LLMSafetyJudgeBaseline:
    """
    LLM-based safety judge baseline.

    Sends each benchmark sample to an LLM with a structured safety prompt
    and parses the JSON response into a safety decision.
    """

    VALID_DECISIONS = {d.value for d in SafetyDecision}

    def __init__(
        self,
        model: str = "gpt-4",
        provider: str = "openai",
        temperature: float = 0.0,
        max_retries: int = 3,
        prompt_version: str = "v1.0",
    ):
        self.model = model
        self.provider = provider
        self.temperature = temperature
        self.max_retries = max_retries
        self.prompt_version = prompt_version
        self.results: List[LLMJudgeResult] = []
        self._prompt_template = self._load_prompt_template()

    def _load_prompt_template(self) -> str:
        prompt_path = os.path.join(
            os.path.dirname(__file__), "prompts", "llm_safety_judge_prompt.md"
        )
        if os.path.exists(prompt_path):
            with open(prompt_path, "r") as f:
                return f.read()
        return ""

    def build_prompt(
        self,
        task_description: str,
        context: str = "",
        risk_context: str = "",
    ) -> str:
        prompt = self._prompt_template
        prompt = prompt.replace("{{task_description}}", task_description)
        prompt = prompt.replace("{{context}}", context)
        prompt = prompt.replace("{{risk_context}}", risk_context)
        return prompt

    def call_llm(self, prompt: str) -> Optional[str]:
        api_key = self._get_api_key()
        if not api_key:
            raise RuntimeError(
                f"No API key found for provider: {self.provider}. "
                f"Set the appropriate environment variable."
            )

        if self.provider == "openai":
            return self._call_openai(prompt, api_key)
        elif self.provider == "deepseek":
            return self._call_deepseek(prompt, api_key)
        elif self.provider == "dashscope":
            return self._call_dashscope(prompt, api_key)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def _get_api_key(self) -> Optional[str]:
        key_map = {
            "openai": "OPENAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "dashscope": "DASHSCOPE_API_KEY",
            "qwen": "QWEN_API_KEY",
        }
        env_var = key_map.get(self.provider, f"{self.provider.upper()}_API_KEY")
        return os.environ.get(env_var)

    def _call_openai(self, prompt: str, api_key: str) -> str:
        try:
            import openai

            client = openai.OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a safety judge. Respond only with valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
            )
            return response.choices[0].message.content
        except ImportError:
            raise RuntimeError("openai package not installed. Run: pip install openai")

    def _call_deepseek(self, prompt: str, api_key: str) -> str:
        try:
            import openai

            client = openai.OpenAI(
                api_key=api_key, base_url="https://api.deepseek.com/v1"
            )
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a safety judge. Respond only with valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
            )
            return response.choices[0].message.content
        except ImportError:
            raise RuntimeError("openai package not installed. Run: pip install openai")

    def _call_dashscope(self, prompt: str, api_key: str) -> str:
        try:
            import openai

            client = openai.OpenAI(
                api_key=api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a safety judge. Respond only with valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
            )
            return response.choices[0].message.content
        except ImportError:
            raise RuntimeError("openai package not installed. Run: pip install openai")

    def parse_output(self, raw_output: str) -> Tuple[Optional[str], Optional[str]]:
        json_match = re.search(r"\{[^{}]*\}", raw_output, re.DOTALL)
        if not json_match:
            return None, None

        try:
            parsed = json.loads(json_match.group())
        except json.JSONDecodeError:
            return None, None

        decision = parsed.get("decision", "")
        rationale = parsed.get("rationale", "")

        if decision not in self.VALID_DECISIONS:
            return None, rationale

        return decision, rationale

    def judge_sample(
        self,
        sample_id: str,
        task_description: str,
        context: str = "",
        risk_context: str = "",
    ) -> LLMJudgeResult:
        prompt = self.build_prompt(task_description, context, risk_context)

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                raw_output = self.call_llm(prompt)
                decision, rationale = self.parse_output(raw_output)

                if decision is not None:
                    return LLMJudgeResult(
                        sample_id=sample_id,
                        decision=decision,
                        rationale=rationale or "",
                        raw_output=raw_output,
                        parse_success=True,
                        retry_count=attempt,
                    )
                else:
                    last_error = f"Parse failure on attempt {attempt + 1}"
            except Exception as e:
                last_error = str(e)
                if attempt < self.max_retries:
                    time.sleep(2 ** (attempt + 1))

        return LLMJudgeResult(
            sample_id=sample_id,
            decision="PARSE_FAILURE",
            rationale="",
            raw_output="",
            parse_success=False,
            retry_count=self.max_retries,
            error=last_error,
        )

    def judge_dataset(self, samples: List[Dict]) -> List[LLMJudgeResult]:
        self.results = []
        for sample in samples:
            result = self.judge_sample(
                sample_id=sample.get("sample_id", ""),
                task_description=sample.get("task_description", ""),
                context=sample.get("context", ""),
                risk_context=sample.get("risk_context", ""),
            )
            self.results.append(result)
        return self.results

    def get_summary(self) -> Dict:
        if not self.results:
            return {"total": 0}

        total = len(self.results)
        parse_success = sum(1 for r in self.results if r.parse_success)
        parse_failure = total - parse_success
        total_retries = sum(r.retry_count for r in self.results)

        decision_counts = {}
        for r in self.results:
            if r.parse_success:
                decision_counts[r.decision] = decision_counts.get(r.decision, 0) + 1

        return {
            "total": total,
            "parse_success": parse_success,
            "parse_failure": parse_failure,
            "total_retries": total_retries,
            "decision_distribution": decision_counts,
        }
