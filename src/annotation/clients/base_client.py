"""Abstract base client for Ollama-based annotation.

Provides rate limiting, retry logic with tenacity, and the interface
that Qwen and Gemma clients implement.
"""

from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import requests

logger = logging.getLogger(__name__)


class BaseClient(ABC):
    """Abstract base for Ollama annotation clients.

    Subclasses must implement :meth:`annotate` and set
    :attr:`model_id` and :attr:`default_timeout`.
    """

    model_id: str = ""
    default_timeout: int = 20

    def __init__(
        self,
        endpoint: str = "http://localhost:11434",
        options: Optional[Dict[str, Any]] = None,
        min_interval: float = 0.0,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.options = options or {}
        if "model_id" in self.options:
            self.model_id = self.options["model_id"]
        self.min_interval = min_interval
        self._last_call_time: float = 0.0
        self._health_checked: bool = False

    def unload(self) -> None:
        """Explicitly unload the model from VRAM by setting keep_alive to 0."""
        payload = {
            "model": self.model_id,
            "prompt": "",
            "stream": False,
            "keep_alive": 0
        }
        try:
            requests.post(f"{self.endpoint}/api/generate", json=payload, timeout=10)
            logger.info("Explicitly unloaded model '%s' from Ollama VRAM.", self.model_id)
        except Exception as exc:
            logger.warning("Failed to unload model '%s': %s", self.model_id, exc)

    def _rate_limit(self) -> None:
        """Block until min_interval seconds have passed since last call."""
        if self.min_interval > 0:
            elapsed = time.time() - self._last_call_time
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
        self._last_call_time = time.time()

    def health_check(self) -> Dict[str, Any]:
        """Verify the model is loaded in Ollama. Raises RuntimeError if unavailable."""
        if self._health_checked:
            return {"models": [{"name": self.model_id}]}
            
        try:
            resp = requests.get(f"{self.endpoint}/api/tags", timeout=5)
            resp.raise_for_status()
            tags = resp.json()
            available = [m["name"] for m in tags.get("models", [])]
            if not any(self.model_id in m for m in available):
                raise RuntimeError(
                    f"Model '{self.model_id}' not found in Ollama. "
                    f"Available: {available}. Please run 'ollama pull {self.model_id}' first."
                )
            self._health_checked = True
            logger.info("Health check passed for model '%s'", self.model_id)
            return tags
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Cannot connect to Ollama server at '{self.endpoint}' (Error: {exc}). "
                "Please make sure Ollama is running."
            )

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
        reraise=True,
    )
    def _post_generate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST to /api/generate with retry logic."""
        self._rate_limit()
        resp = requests.post(
            f"{self.endpoint}/api/generate",
            json=payload,
            timeout=self.options.get("timeout", self.default_timeout),
        )
        resp.raise_for_status()
        return resp.json()

    def annotate(self, title: str, sapo: str) -> Dict[str, Any]:
        """Annotate a single headline.

        Parameters
        ----------
        title : str
            The headline text (Vietnamese).
        sapo : str
            The article summary / lead paragraph.

        Returns
        -------
        dict with keys: label, confidence, rubric_scores, severity, reason, thought_process
        """
        prompt = self._build_prompt(
            self.options.get("system_prompt", ""), title, sapo
        )
        payload = {
            "model": self.model_id,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "num_ctx": self.options.get("num_ctx", 2048),
                "num_batch": self.options.get("num_batch", 256),
                "temperature": self.options.get("temperature", 0.1),
            },
        }
        try:
            result = self._post_generate(payload)
            response_text = result.get("response", "")
            think_content = result.get("thinking", "")

            # If response is empty but thinking has content (typical for Ollama format with reasoning models), use thinking
            if not response_text.strip() and think_content:
                response_text = think_content

            parsed = self._clean_and_parse_json(response_text)
            
            # Preserve thought process if it was in Ollama's separate thinking field
            if think_content:
                if "thought_process" not in parsed:
                    parsed["thought_process"] = {}
                if isinstance(parsed["thought_process"], dict) and "external_reasoning" not in parsed["thought_process"]:
                    parsed["thought_process"]["external_reasoning"] = think_content

            return self._normalize(parsed)
        except Exception as exc:
            raw_resp = result.get("response") if 'result' in locals() else None
            raw_think = result.get("thinking") if 'result' in locals() else None
            logger.error("%s annotation failed: %s | Raw response: %r | Thinking: %r", self.__class__.__name__, exc, raw_resp, raw_think)
            return {
                "label": None,
                "confidence": 0.0,
                "rubric_scores": [0, 0, 0, 0],
                "severity": None,
                "reason": f"Error: {exc}",
                "thought_process": {},
            }

    def _build_prompt(self, system_prompt: str, title: str | None, sapo: str | None) -> str:
        """Replace {title} and {sapo} placeholders in the system prompt after cleaning double quotes."""
        title_clean = (title or "").replace('"', "'")
        sapo_clean = (sapo or "").replace('"', "'")
        return system_prompt.replace("{title}", title_clean).replace("{sapo}", sapo_clean)

    def _repair_json_string_quotes(self, json_str: str) -> str:
        """Sanitize unescaped double quotes in JSON text fields to avoid parsing errors."""
        string_keys = {
            "c1_sensationalism_analysis",
            "c2_information_gap_analysis",
            "c3_syntactic_framing_analysis",
            "c4_incongruence_analysis",
            "reason",
            "external_reasoning"
        }
        lines = json_str.splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped.endswith('"') and not stripped.endswith('",'):
                continue
            if ":" not in stripped:
                continue
            
            match_key = re.match(r'^\s*"([a-zA-Z0-9_]+)"\s*:\s*"', line)
            if not match_key:
                continue
            
            key = match_key.group(1)
            if key not in string_keys:
                continue
                
            prefix_len = len(match_key.group(0))
            suffix = '",' if line.endswith('",') else '"'
            suffix_len = len(suffix)
            
            value_content = line[prefix_len:-suffix_len]
            cleaned_value = value_content.replace('"', "'").replace('\\"', "'")
            lines[i] = line[:prefix_len] + cleaned_value + suffix
            
        return "\n".join(lines)

    def _clean_and_parse_json(self, response_text: str) -> Dict[str, Any]:
        """Strip thinking tags, extract the JSON object, repair internal quotes, and parse."""
        # 1. Strip think tags
        cleaned = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL).strip()
        
        # 2. Extract JSON block (first '{' to last '}')
        json_match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if json_match:
            cleaned = json_match.group(0)
            
        # 3. Try parsing directly first
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # 4. If direct parse fails, try to repair unescaped quotes in string fields
            try:
                repaired = self._repair_json_string_quotes(cleaned)
                return json.loads(repaired)
            except json.JSONDecodeError as exc:
                raise exc

    def _normalize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure the parsed JSON has all required fields with correct types, hoisting nested fields if needed."""
        tp = data.get("thought_process", {})
        if isinstance(tp, dict):
            for key in ["label", "severity", "confidence", "reason"]:
                if data.get(key) is None and key in tp:
                    data[key] = tp[key]
            # Hoist rubric_scores if the top level has default/empty scores
            if (data.get("rubric_scores") is None or data.get("rubric_scores") == [0, 0, 0, 0]) and "rubric_scores" in tp:
                data["rubric_scores"] = tp["rubric_scores"]

        label = data.get("label")
        if label is not None:
            try:
                label = max(0, min(1, int(label)))
            except (ValueError, TypeError):
                label = None
                
        severity = data.get("severity")
        if severity is not None:
            try:
                severity = int(severity)
            except (ValueError, TypeError):
                severity = None
                
        scores = data.get("rubric_scores", [0, 0, 0, 0])
        if not isinstance(scores, list) or len(scores) != 4:
            scores = [0, 0, 0, 0]
        else:
            cleaned_scores = []
            for s in scores:
                try:
                    cleaned_scores.append(max(0, min(2, int(s))))
                except (ValueError, TypeError):
                    cleaned_scores.append(0)
            scores = cleaned_scores
            
        confidence = data.get("confidence", 0.0)
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (ValueError, TypeError):
            confidence = 0.0
            
        return {
            "label": label,
            "confidence": confidence,
            "rubric_scores": scores,
            "severity": severity,
            "reason": str(data.get("reason", "")),
            "thought_process": tp if isinstance(tp, dict) else {},
        }
