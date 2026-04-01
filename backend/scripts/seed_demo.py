#!/usr/bin/env python3
"""
Seed script — регистрирует демо-агентов для хакатон-демо.

Создаёт двух агентов через API:
  - @agentshub-demo/text-summarizer
  - @agentshub-demo/sentiment-analyzer

Требует: работающий backend (localhost:8000) и зарегистрированного юзера.

Использование:
    python scripts/seed_demo.py --base-url http://localhost:8000 --token <JWT>
"""
import argparse
import io
import json
import zipfile
import sys
import httpx


DEMO_AGENTS = [
    {
        "manifest": {
            "name": "text-summarizer",
            "version": "1.0.0",
            "description": "Summarizes long text into a concise summary using Claude AI",
            "entrypoint": "agent.py",
            "input_schema": {
                "text": {"type": "string", "description": "Text to summarize"},
                "language": {"type": "string", "default": "en"},
            },
            "output_schema": {
                "summary": {"type": "string"},
                "word_count": {"type": "integer"},
            },
            "capabilities": ["summarization", "nlp", "text-processing"],
            "tags": ["text", "summarization", "nlp"],
            "category": "text-processing",
            "price_per_call": 0.001,
            "timeout_seconds": 30,
        },
        "agent_code": '''#!/usr/bin/env python3
import sys
import json
import os

def main():
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}))
        sys.exit(1)

    text = data.get("text", "")
    if not text:
        print(json.dumps({"error": "text field is required"}))
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        # Fallback: первые 200 символов
        summary = text[:200] + ("..." if len(text) > 200 else "")
        print(json.dumps({"summary": summary, "word_count": len(text.split())}))
        return

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": f"Summarize in 2-3 sentences:\\n\\n{text}"}],
    )
    summary = msg.content[0].text.strip()
    print(json.dumps({"summary": summary, "word_count": len(text.split())}))

if __name__ == "__main__":
    main()
''',
    },
    {
        "manifest": {
            "name": "sentiment-analyzer",
            "version": "1.0.0",
            "description": "Analyzes sentiment of text (positive/negative/neutral) with confidence score",
            "entrypoint": "agent.py",
            "input_schema": {
                "text": {"type": "string", "description": "Text to analyze"},
            },
            "output_schema": {
                "sentiment": {"type": "string", "enum": ["positive", "negative", "neutral"]},
                "confidence": {"type": "number"},
                "explanation": {"type": "string"},
            },
            "capabilities": ["sentiment-analysis", "nlp", "text-processing"],
            "tags": ["text", "sentiment", "nlp"],
            "category": "text-processing",
            "price_per_call": 0.0005,
            "timeout_seconds": 30,
        },
        "agent_code": '''#!/usr/bin/env python3
import sys
import json
import os

def main():
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}))
        sys.exit(1)

    text = data.get("text", "")
    if not text:
        print(json.dumps({"error": "text field is required"}))
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        pos_words = ["good", "great", "excellent", "happy", "love", "amazing", "awesome"]
        neg_words = ["bad", "terrible", "hate", "awful", "poor", "horrible"]
        t = text.lower()
        pos = sum(1 for w in pos_words if w in t)
        neg = sum(1 for w in neg_words if w in t)
        if pos > neg:
            result = {"sentiment": "positive", "confidence": 0.7, "explanation": "Contains positive keywords"}
        elif neg > pos:
            result = {"sentiment": "negative", "confidence": 0.7, "explanation": "Contains negative keywords"}
        else:
            result = {"sentiment": "neutral", "confidence": 0.5, "explanation": "No strong sentiment indicators"}
        print(json.dumps(result))
        return

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": f\'\'\'Analyze sentiment. Return ONLY JSON:
{{"sentiment": "positive" or "negative" or "neutral", "confidence": 0.0-1.0, "explanation": "brief"}}

Text: {text}\'\'\'}],
    )
    raw = msg.content[0].text.strip()
    start, end = raw.find("{"), raw.rfind("}") + 1
    if start == -1:
        print(json.dumps({"error": "AI returned invalid response"}))
        sys.exit(1)
    print(raw[start:end])

if __name__ == "__main__":
    main()
''',
    },
]


def _make_zip(manifest: dict, agent_code: str) -> bytes:
    """Создаёт zip с agent.py и manifest.json."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("agent.py", agent_code)
        zf.writestr("requirements.txt", "anthropic>=0.40.0\n")
    return buf.getvalue()


def seed(base_url: str, token: str) -> None:
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client(base_url=base_url, timeout=30) as client:
        # Проверяем auth
        me = client.get("/api/v1/auth/me", headers=headers)
        if me.status_code != 200:
            print(f"ERROR: Auth failed ({me.status_code}): {me.text}")
            sys.exit(1)
        user = me.json()
        print(f"Seeding as: {user.get('wallet_address', '?')}")

        for agent_def in DEMO_AGENTS:
            name = agent_def["manifest"]["name"]
            zip_bytes = _make_zip(agent_def["manifest"], agent_def["agent_code"])

            resp = client.post(
                "/api/v1/agents",
                headers=headers,
                files={"bundle": (f"{name}.zip", zip_bytes, "application/zip")},
            )

            if resp.status_code in (200, 201):
                data = resp.json()
                print(f"  ✓ {data['slug']}")
                if data.get("on_chain_address"):
                    print(f"    on-chain PDA: {data['on_chain_address']}")
            else:
                print(f"  ✗ {name}: {resp.status_code} — {resp.text[:200]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed demo agents for AgentsHub hackathon demo")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--token", required=True, help="JWT token from /api/v1/auth/login")
    args = parser.parse_args()

    seed(args.base_url, args.token)
    print("Done.")
