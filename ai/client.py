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

    for m in models:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models"
            f"/{m}:generateContent?key={api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.3,
                "maxOutputTokens": 2048,
            },
        }
        try:
            resp = requests.post(url, json=payload, timeout=30)
            if resp.status_code == 200:
                return _parse_response(resp)
            if resp.status_code in _RETRY_STATUSES:
                sleep_time = _OVERLOAD_SLEEP if resp.status_code == 503 else 2
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
    """Extract and parse JSON from Gemini response."""
    try:
        text = (
            resp.json()
            .get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
            .strip()
        )
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
        return json.loads(text)
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"  [AI] Parse error: {e}")
        return {}
