#!/usr/bin/env python3
"""
Sentiment Analyzer Agent — AgentsHub Example
Анализирует тональность текста (positive/negative/neutral).

Использование:
  echo '{"text": "This is amazing!"}' | python agent.py
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
    if not text:
        print(json.dumps({"error": "text field is required"}))
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        # Fallback: keyword-based sentiment
        positive_words = ["good", "great", "excellent", "happy", "love", "amazing", "awesome", "хорошо", "отлично"]
        negative_words = ["bad", "terrible", "hate", "awful", "poor", "horrible", "плохо", "ужасно"]
        text_lower = text.lower()
        pos = sum(1 for w in positive_words if w in text_lower)
        neg = sum(1 for w in negative_words if w in text_lower)
        if pos > neg:
            result = {"sentiment": "positive", "confidence": 0.7, "explanation": "Contains positive keywords"}
        elif neg > pos:
            result = {"sentiment": "negative", "confidence": 0.7, "explanation": "Contains negative keywords"}
        else:
            result = {"sentiment": "neutral", "confidence": 0.5, "explanation": "No strong sentiment indicators"}
        print(json.dumps(result))
        return

    import anthropic

    prompt = f"""Analyze the sentiment of the following text.

Return ONLY valid JSON:
{{"sentiment": "positive" or "negative" or "neutral", "confidence": 0.0 to 1.0, "explanation": "brief reason"}}

Text: {text}"""

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1:
        print(json.dumps({"error": "AI returned invalid response"}))
        sys.exit(1)

    result = json.loads(raw[start:end])
    print(json.dumps(result))


if __name__ == "__main__":
    main()
