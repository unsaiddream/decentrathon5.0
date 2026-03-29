# AgentsHub Agent SDK

Всё что нужно для создания и публикации AI-агента на AgentsHub.

## Структура агента

Каждый агент — это `.zip` файл со следующей структурой:

```
my-agent.zip
├── manifest.json      # обязательно
├── agent.py           # entrypoint (имя задаётся в manifest)
└── requirements.txt   # опционально — pip зависимости
```

## manifest.json

Полная схема: [manifest.schema.json](./manifest.schema.json)

Минимальный пример:

```json
{
  "name": "my-agent",
  "version": "1.0.0",
  "description": "What your agent does",
  "author": "YOUR_SOLANA_WALLET_ADDRESS",
  "entrypoint": "agent.py",
  "runtime": "python3.11",
  "price_per_call": 0.001,
  "timeout_seconds": 30,
  "input_schema": {
    "type": "object",
    "required": ["text"],
    "properties": {
      "text": { "type": "string" }
    }
  },
  "output_schema": {
    "type": "object"
  },
  "tags": ["nlp"],
  "category": "nlp",
  "uses_agents": []
}
```

## Контракт агента

Платформа запускает агент как subprocess:

```
echo '{"text": "..."}' | python3 agent.py
```

**stdin** → JSON с входными данными (соответствует `input_schema`)
**stdout** → JSON с результатом (соответствует `output_schema`)
**exit code 0** → успех
**exit code != 0** → ошибка (stderr показывается как `error` в execution)

```python
import json, sys

def main():
    data = json.loads(sys.stdin.read())   # читаем input
    result = process(data)
    print(json.dumps(result))             # пишем output

if __name__ == "__main__":
    main()
```

## Быстрый старт

### 1. Скопируй пример

```bash
cp -r example-agent my-agent
cd my-agent
```

### 2. Измени manifest.json

- `name` — уникальное имя (kebab-case)
- `author` — твой Solana кошелёк
- `price_per_call` — цена в SOL
- `input_schema` / `output_schema` — описание входных/выходных данных

### 3. Напиши агент

Редактируй `agent.py`. Основное правило: читай stdin, пиши в stdout.

### 4. Тестируй локально

```bash
echo '{"text": "Hello world. This is a test.", "max_sentences": 1}' | python3 agent.py
```

### 5. Собери zip

```bash
cd ..
./build.sh my-agent
# → my-agent.zip
```

### 6. Загрузи на платформу

Открой [http://localhost:8001/ui/upload.html](http://localhost:8001/ui/upload.html), перетащи `my-agent.zip`.

## Зависимости

Если твой агент использует внешние библиотеки — добавь `requirements.txt`:

```
openai==1.40.0
httpx==0.27.2
```

Платформа автоматически установит зависимости перед запуском.

> **Лимиты:**
> - Максимальный размер bundle: **50 MB**
> - Максимальное время выполнения: `timeout_seconds` (до 300s)
> - Runtime: Python 3.10, 3.11, 3.12

## Composable агенты

Агент может вызывать другие агенты через HTTP API платформы.
Укажи их в `uses_agents`:

```json
"uses_agents": ["abc12345/text-summarizer", "def67890/translator"]
```

Платформа автоматически проверит баланс и спишет плату за каждый вызов.

## Пример агента

Смотри [`example-agent/`](./example-agent/) — полностью рабочий агент суммаризации текста без внешних зависимостей.
