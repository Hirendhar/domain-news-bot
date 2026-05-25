"""
Gemini AI client with automatic model fallback on quota/overload.
Free tier: 500 req/day on gemini-2.0-flash-lite, 1M tokens/day.
"""
import os
import json
import time
import requests

_last_call: float = 0.0

MODEL_FALLBACK = [
    "gemini-2.5-flash",          # confirmed working on this key
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-flash-lite-latest",
]

# Status codes that trigger model fallback (not hard failures)
_RETRY_STATUSES = {
    429,   # quota exhausted — try next model
    404,   # model not available
    503,   # model overloaded (transient) — wait longer before next model
}
_OVERLOAD_SLEEP = 15.0   # extra wait on 503 before trying next model
_BACKOFF_BASE = 3.0      # base seconds for escalating 429 backoff (3, 6, 12, ...)


def generate(prompt: str, model: str = "", rate_limit: float = 7.0) -> dict:
    """
    Call Gemini API with auto-fallback on 429/404/503.
    Returns parsed JSON dict, or {} on all-models failure.
    """
    global _last_call

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("  [AI] GEMINI_API_KEY not set — skipping enrichment")
        return {}

    # Rate limiting: enforce minimum gap between calls
    elapsed = time.time() - _last_call
    if elapsed < rate_limit:
        time.sleep(rate_limit - elapsed)

    models = [model] + [m for m in MODEL_FALLBACK if m != model] if model else MODEL_FALLBACK
    _last_call = time.time()

    for idx, m in enumerate(models):
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models"
            f"/{m}:generateContent?key={api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.3,
                "maxOutputTokens": 8192,   # headroom for larger batches (avoids JSON truncation)
            },
        }
        try:
            resp = requests.post(url, json=payload, timeout=45)
            if resp.status_code == 200:
                return _parse_response(resp)
            if resp.status_code in _RETRY_STATUSES:
                if resp.status_code == 503:
                    sleep_time = _OVERLOAD_SLEEP
                else:
                    # Escalating backoff on rate-limit/quota — each model waits a bit longer
                    sleep_time = _BACKOFF_BASE * (2 ** idx)
                print(f"  [AI] {m} returned {resp.status_code} — waiting {sleep_time:.0f}s, trying next model")
                time.sleep(sleep_time)
                continue
            print(f"  [AI] {m} returned {resp.status_code}: {resp.text[:200]}")
            return {}
        except requests.RequestException as e:
            print(f"  [AI] Request error on {m}: {e}")
            return {}

    print("  [AI] All models exhausted")
    return {}


def _parse_response(resp: requests.Response) -> dict:
    """Extract and parse JSON from Gemini response, salvaging truncated output."""
    try:
        text = (
            resp.json()
            .get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
            .strip()
        )
    except (KeyError, IndexError) as e:
        print(f"  [AI] Response shape error: {e}")
        return {}

    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Response was likely truncated (hit token limit mid-string).
        # Salvage any complete analysis objects from the partial JSON.
        salvaged = _salvage_analyses(text)
        if salvaged:
            print(f"  [AI] Recovered {len(salvaged)} analyses from truncated response")
            return {"analyses": salvaged}
        print(f"  [AI] Parse error: {e}")
        return {}


def _salvage_analyses(text: str) -> list[dict]:
    """
    Extract complete top-level objects from a truncated `"analyses": [...]` array.
    Scans with brace-depth tracking so a half-written final object is dropped
    while all preceding complete objects are recovered.
    """
    start = text.find('"analyses"')
    if start == -1:
        return []
    bracket = text.find("[", start)
    if bracket == -1:
        return []

    objects: list[dict] = []
    depth = 0
    in_str = False
    escape = False
    obj_start = -1

    for i in range(bracket + 1, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and obj_start != -1:
                chunk = text[obj_start:i + 1]
                try:
                    objects.append(json.loads(chunk))
                except json.JSONDecodeError:
                    pass
                obj_start = -1
    return objects
