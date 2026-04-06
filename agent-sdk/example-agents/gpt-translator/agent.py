#!/usr/bin/env python3
"""
GPT Translator Agent
Translates text between languages using Claude AI.

stdin  -> {"text": "Hello world", "options": {"target_lang": "ru"}}
stdout -> {"translated": "...", "source_lang": "en", "target_lang": "ru"}
"""
import sys
import json
import os


# Basic translation dictionary for fallback
BASIC_TRANSLATIONS = {
    "en_ru": {
        "hello": "привет", "world": "мир", "good": "хороший", "bad": "плохой",
        "yes": "да", "no": "нет", "thank you": "спасибо", "please": "пожалуйста",
        "how are you": "как дела", "goodbye": "до свидания", "morning": "утро",
        "night": "ночь", "day": "день", "love": "любовь", "friend": "друг",
        "work": "работа", "home": "дом", "time": "время", "water": "вода",
        "food": "еда", "the": "", "is": "это", "are": "это", "a": "",
        "i": "я", "you": "ты", "he": "он", "she": "она", "we": "мы",
        "and": "и", "or": "или", "but": "но", "this": "это", "that": "то",
        "amazing": "удивительный", "great": "отличный", "project": "проект",
        "intelligence": "интеллект", "artificial": "искусственный",
        "decentralized": "децентрализованный", "agent": "агент", "agents": "агенты",
        "marketplace": "маркетплейс", "blockchain": "блокчейн",
    },
    "en_es": {
        "hello": "hola", "world": "mundo", "good": "bueno", "bad": "malo",
        "yes": "si", "no": "no", "thank you": "gracias", "please": "por favor",
        "the": "el", "is": "es", "are": "son",
    },
}


def detect_lang(text):
    cyrillic = sum(1 for c in text if '\u0400' <= c <= '\u04ff')
    latin = sum(1 for c in text if 'a' <= c.lower() <= 'z')
    if cyrillic > latin:
        return "ru"
    return "en"


def fallback_translate(text, target_lang):
    source_lang = detect_lang(text)
    key = f"{source_lang}_{target_lang}"
    dictionary = BASIC_TRANSLATIONS.get(key, {})

    if not dictionary:
        return {
            "translated": text,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "note": f"No fallback dictionary for {key}, returning original",
        }

    result = text.lower()
    # Sort by length descending to match longer phrases first
    for eng, trans in sorted(dictionary.items(), key=lambda x: -len(x[0])):
        result = result.replace(eng, trans)

    # Clean up double spaces
    import re
    result = re.sub(r'\s+', ' ', result).strip()

    # Capitalize first letter
    if result:
        result = result[0].upper() + result[1:]

    return {
        "translated": result,
        "source_lang": source_lang,
        "target_lang": target_lang,
    }


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

    options = input_data.get("options", {})
    target_lang = options.get("target_lang", "ru")
    source_lang = options.get("source_lang", "auto")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        result = fallback_translate(text, target_lang)
        print(json.dumps(result))
        return

    import anthropic

    lang_hint = f" from {source_lang}" if source_lang != "auto" else ""
    prompt = f"""Translate the following text{lang_hint} to {target_lang}.

Return ONLY valid JSON:
{{"translated": "translated text", "source_lang": "detected source language code", "target_lang": "{target_lang}"}}

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
