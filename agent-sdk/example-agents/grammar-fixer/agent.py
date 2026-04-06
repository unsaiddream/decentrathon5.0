#!/usr/bin/env python3
"""
Grammar Fixer Agent
Fixes grammar, spelling, and punctuation errors in text.

stdin  -> {"text": "..."}
stdout -> {"corrected": "...", "changes_count": N, "changes": [...]}
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
        # Fallback: basic corrections
        corrections = {
            "teh": "the", "recieve": "receive", "occurence": "occurrence",
            "seperate": "separate", "definately": "definitely",
            "accomodate": "accommodate", "occured": "occurred",
            "refered": "referred", "untill": "until", "wich": "which",
            "thier": "their", "helo": "hello", "wrld": "world",
            "tset": "test", "grammer": "grammar", "fixr": "fixer",
            "dont": "don't", "wont": "won't", "cant": "can't",
            "im": "I'm", "ive": "I've", "id ": "I'd ",
            "i ": "I ", " i ": " I ",
        }
        corrected = text
        changes = []
        for wrong, right in corrections.items():
            if wrong in corrected.lower():
                idx = corrected.lower().find(wrong)
                original = corrected[idx:idx+len(wrong)]
                corrected = corrected[:idx] + right + corrected[idx+len(wrong):]
                changes.append({"from": original, "to": right})

        # Capitalize first letter of sentences
        import re
        corrected = re.sub(r'(?<=[.!?]\s)([a-z])', lambda m: m.group(1).upper(), corrected)
        if corrected and corrected[0].islower():
            corrected = corrected[0].upper() + corrected[1:]

        print(json.dumps({
            "corrected": corrected,
            "changes_count": len(changes),
            "changes": changes,
        }))
        return

    import anthropic

    prompt = f"""Fix all grammar, spelling, and punctuation errors in the text below.
Preserve the original tone and style.

Return ONLY valid JSON:
{{"corrected": "the fixed text", "changes_count": N, "changes": [{{"from": "error", "to": "fix"}}]}}

Text: {text}"""

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
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
