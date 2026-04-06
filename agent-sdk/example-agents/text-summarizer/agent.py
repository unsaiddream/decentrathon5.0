"""
AgentsHub Example Agent: text-summarizer
-----------------------------------------
Reads JSON from stdin, writes JSON to stdout.
Exit code 0 = success, non-zero = failure (stderr message shown as error).

Contract:
  stdin  → {"text": "...", "max_sentences": 3}
  stdout → {"summary": "...", "word_count": N, "reduction_pct": N}
"""

import json
import sys
import re
from collections import Counter
from typing import Any


def extract_sentences(text: str) -> list[str]:
    """Разбиваем текст на предложения простым regex."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in sentences if len(s.strip()) > 10]


def score_sentences(sentences: list[str]) -> list[tuple[int, float]]:
    """Оцениваем каждое предложение по частоте слов."""
    # Собираем все слова
    all_words: list[str] = []
    for s in sentences:
        words = re.findall(r'\b[a-zA-Zа-яА-Я]{3,}\b', s.lower())
        all_words.extend(words)

    freq = Counter(all_words)
    if not freq:
        return [(i, 0.0) for i in range(len(sentences))]

    max_freq = max(freq.values())

    scored = []
    for i, sentence in enumerate(sentences):
        words = re.findall(r'\b[a-zA-Zа-яА-Я]{3,}\b', sentence.lower())
        score = sum(freq[w] / max_freq for w in words) / max(len(words), 1)
        scored.append((i, score))

    return scored


def summarize(text: str, max_sentences: int = 3) -> dict[str, Any]:
    """Основная логика суммаризации."""
    sentences = extract_sentences(text)

    if not sentences:
        return {"summary": text[:200], "word_count": len(text.split()), "reduction_pct": 0.0}

    scored = score_sentences(sentences)

    # Выбираем топ-N по score, сохраняем оригинальный порядок
    top_indices = sorted(
        sorted(scored, key=lambda x: x[1], reverse=True)[:max_sentences],
        key=lambda x: x[0]
    )

    summary = " ".join(sentences[i] for i, _ in top_indices)
    word_count = len(text.split())
    summary_word_count = len(summary.split())
    reduction_pct = round((1 - summary_word_count / max(word_count, 1)) * 100, 1)

    return {
        "summary": summary,
        "word_count": word_count,
        "reduction_pct": reduction_pct,
    }


def main() -> None:
    # Читаем входные данные из stdin
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)

    # Валидируем обязательные поля
    text = data.get("text", "")
    if not text or not isinstance(text, str):
        print("Field 'text' is required and must be a string", file=sys.stderr)
        sys.exit(1)

    max_sentences = data.get("max_sentences", 3)
    if not isinstance(max_sentences, int) or not (1 <= max_sentences <= 10):
        max_sentences = 3

    # Выполняем суммаризацию
    result = summarize(text, max_sentences)

    # Записываем результат в stdout (платформа читает отсюда)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
