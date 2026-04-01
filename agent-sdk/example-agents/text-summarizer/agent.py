#!/usr/bin/env python3
"""
Text Summarizer Agent — AgentsHub Example
Принимает текст, возвращает краткое содержание и 3 ключевых пункта.

Использование:
  echo '{"text": "Long text here...", "language": "en"}' | python agent.py
"""
import sys
import json
import os


def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON input: {e}"}))
        sys.exit(1)

    text = input_data.get("text", "")
    language = input_data.get("language", "en")

    if not text:
        print(json.dumps({"error": "text field is required"}))
        sys.exit(1)

    if len(text) > 10000:
        text = text[:10000]

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        # Fallback без AI
        words = text.split()
        result = {
            "summary": " ".join(words[:20]) + "...",
            "bullets": [
                " ".join(words[:10]) + "...",
                " ".join(words[10:20]) + "...",
                " ".join(words[20:30]) + "...",
            ],
        }
        print(json.dumps(result, ensure_ascii=False))
        return

    import anthropic

    lang_instruction = "Respond in Russian." if language == "ru" else "Respond in English."
    prompt = f"""Summarize the following text.
{lang_instruction}

Return ONLY valid JSON with this exact structure:
{{"summary": "one sentence summary", "bullets": ["point 1", "point 2", "point 3"]}}

Text:
{text}"""

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1:
        print(json.dumps({"error": "AI returned invalid response", "raw": raw[:200]}))
        sys.exit(1)

    result = json.loads(raw[start:end])
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
