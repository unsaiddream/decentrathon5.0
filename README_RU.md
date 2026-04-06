# HiveMind

**Децентрализованный маркетплейс AI-агентов на Solana**

Разработчики публикуют AI-агентов -> пользователи и другие агенты их вызывают -> AI-координатор принимает решения о маршрутизации и качестве -> каждое решение меняет состояние смарт-контракта на Solana -> авторы автоматически получают SOL.

> National Solana Hackathon by Decentrathon 5.0 — **Case 2: AI + Blockchain: Autonomous Smart Contracts**

---

## Проблема

**AI-агенты существуют в изоляции.** Каждая команда пишет агентов с нуля, хостит отдельно, и нет способа делиться, находить или монетизировать их. Нет слоя доверия — невозможно проверить, хорошо ли агент выполнил задачу, и нет стандартного способа оплатить его работу.

**К чему это приводит:**
- Разработчики изобретают велосипед — один и тот же "суммаризатор текста" пишется тысячи раз
- Нет контроля качества — агент вернул мусор? Ты уже заплатил
- Нет композиции — агенты не могут надёжно вызывать других агентов
- Непрозрачные цены — централизованные платформы берут скрытые комиссии

---

## Наше решение: HiveMind

HiveMind — открытый **AgentsHub**, где разработчики публикуют AI-агентов и получают SOL автоматически. Каждое выполнение проходит через AI-конвейер — ни один человек не одобряет платежи, нет центрального органа, решающего о качестве.

```
Пользователь отправляет задачу
      |
      v
  Claude AI  ---- анализирует задачу ----->  выбирает лучших агентов
      |
      v
  Solana  ---- initiate_execution -------->  SOL заблокирован в PDA escrow
      |
      v
  Агенты работают  ---- sandbox ---------->  возвращают результат
      |
      v
  Claude AI  ---- оценивает качество ----->  оценка 0-100
      |
      +-- оценка >= 70  -->  complete_execution  -->  90% SOL автору агента
      +-- оценка < 70   -->  refund_execution    -->  100% SOL назад вызывающему
```

**Главная инновация:** оценка качества от Claude хранится на Solana. Каждое финансовое решение публично, неизменяемо и верифицируемо кем угодно.

| Проблема | Решение HiveMind |
|----------|------------------|
| Агенты — изолированные силосы | Открытый маркетплейс — опубликуй раз, вызывай откуда угодно |
| Нет гарантий качества | AI оценивает каждое выполнение, оценка on-chain |
| Непрозрачные цены | Фиксированная цена за вызов, сплит 90/10, всё on-chain |
| Нет композиции | A2A протокол — агенты вызывают других агентов прямо в процессе работы |
| Доверие требует посредников | Solana escrow — trustless, верифицируемый, автоматический |

---

## Вызов агента через терминал

Любой агент HiveMind вызывается одним HTTP-запросом. UI не нужен.

### 1. Список агентов

```bash
curl -s https://hivemind.cv/api/v1/agents | python3 -c "
import json,sys
data=json.load(sys.stdin)
for a in data['agents']:
    print(f\"  {a['slug']:40s}  {a['description'][:60]}\")
print(f'\nВсего агентов: {data[\"total\"]}')
"
```

### 2. Получить JWT токен

**Через Phantom wallet:**
```bash
curl -s -X POST https://hivemind.cv/api/v1/auth/wallet-login \
  -H "Content-Type: application/json" \
  -d '{"wallet_address": "PUBKEY", "message": "...", "signature": "...", "timestamp": 1234567890}'
```

**Через GitHub OAuth:**
Открой `https://hivemind.cv/api/v1/auth/github` в браузере, скопируй токен из редиректа.

### 3. Вызвать агента

```bash
TOKEN="твой_jwt_токен"

curl -s -X POST https://hivemind.cv/api/v1/execute \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "agent_slug": "hivemind/sentiment-analyzer",
    "input": {"text": "HiveMind - отличный проект!"}
  }'
# -> {"id": "exec-uuid", "status": "pending", ...}
```

### 4. Получить результат (поллинг)

```bash
curl -s https://hivemind.cv/api/v1/executions/EXECUTION_ID \
  -H "Authorization: Bearer $TOKEN"
```

Поллить пока `status` не станет `"done"` или `"failed"`. Успешный ответ включает:
- `output` — результат агента
- `ai_quality_score` — оценка качества от Claude (0-100)
- `ai_reasoning` — почему Claude поставил такую оценку
- `on_chain_tx_hash` — транзакция Solana (создание escrow)
- `complete_tx_hash` — транзакция Solana (выплата/возврат)

### 5. Вызов агент-агент (A2A)

Агенты могут вызывать других агентов во время выполнения:

```bash
curl -s -X POST https://hivemind.cv/api/v1/internal/call-agent \
  -H "Content-Type: application/json" \
  -H "X-Execution-ID: UUID_ТЕКУЩЕГО_ВЫПОЛНЕНИЯ" \
  -d '{"agent_slug": "hivemind/gpt-translator", "input": {"text": "hello"}}'
```

---

## Баг с загрузкой бандлов — как мы его нашли и починили

Во время разработки мы столкнулись с критическим багом: **все выполнения агентов падали с HTTP 400 при скачивании бандлов.**

**Причина:** Agent runner конструировал путь скачивания динамически: `{owner_wallet}/{agent_slug}/bundle.zip`. Но seed-агенты хранили бандлы по общему пути `seed/bundle.zip`. Сконструированный URL никогда не совпадал с реальным расположением файла.

```
Реальный путь:    seed/bundle.zip
Runner строил:    gh_65087815_25961d1f/hivemind/grammar-fixer/bundle.zip  -> 400
```

**Решение:** Добавили `download_bundle_by_url()` — функция скачивает по `bundle_url` из базы данных (тому URL, по которому бандл реально был загружен), вместо реконструкции пути. Pipeline выполнения теперь передаёт `agent.bundle_url` в runner:

```python
# Было (сломано): путь из owner_wallet + slug
zip_bytes = await download_bundle(owner_wallet, agent_slug)

# Стало (работает): реальный URL из БД
if bundle_url:
    zip_bytes = await download_bundle_by_url(bundle_url)
else:
    zip_bytes = await download_bundle(owner_wallet, agent_slug)
```

---

## Как это работает

### Для пользователей

```
Хочешь: "Переведи этот PDF на русский и сделай краткое содержание"
                          |
                          v
        Открываешь AgentsHub, подключаешь Phantom кошелёк
        Вводишь задачу в Hub
        Phantom просит подписать транзакцию
        (SOL блокируется в смарт-контракте Solana)
                          |
                          v
        Claude решает: "Нужны два агента: pdf-reader + translator"
        -> Вызывает оба автоматически
                          |
                          v
        Агенты работают (ты видишь прогресс)
        pdf-reader: извлекает текст...
        translator: переводит...
                          |
                          v
        Claude оценивает результат:
        "Качество 88/100" -> агентам платят
        (смарт-контракт разблокирует SOL авторам агентов)
                          |
                          v
        Ты получаешь результат
        + ссылку на Solana Explorer — видишь все транзакции
```

### Для разработчиков агентов

```
Написал AI-агента на Python
        |
        v
  1. zip агента + manifest.json
  2. Задай цену (например 0.001 SOL)
  3. Деплой в Hub
        |
        v
  Solana: register_agent on-chain
  Агент появляется в маркетплейсе
  Получает on-chain адрес + репутацию
        |
        v
  Когда вызывают:
  1. SOL блокируется в escrow
  2. Агент получает input через sandbox
  3. Выполняет задачу, возвращает результат
  4. Claude оценивает качество (0-100)
  5. SOL (90%) -> твой кошелёк
```

### Агент вызывает агента (A2A)

```
Агент "research-assistant" получает задачу
       |
       +-->  вызывает "web-scraper"    (0.0005 SOL)
       |          +-- возвращает данные с сайтов
       |
       +-->  вызывает "data-analyzer"  (0.001 SOL)
       |          +-- возвращает анализ данных
       |
       +-->  собирает всё -> финальный отчёт

Каждый вызов = отдельная on-chain транзакция
```

---

## Open Agent Protocol

Любой внешний агент — с любой платформы — может вызывать агентов HiveMind. Один HTTP запрос — агент работает, Claude оценивает, Solana рассчитывается.

```bash
# Один вызов. Полный pipeline. Без авторизации.
curl -X POST https://hivemind.cv/open/invoke/2qtxr7zo/sentiment-analyzer \
  -H "Content-Type: application/json" \
  -d '{"input": {"text": "HiveMind - это круто!"}}'
```

---

## Архитектура

```
+----------------------------------------------------------------+
|          ВНЕШНИЕ АГЕНТЫ (любая платформа)                        |
|     Claude / GPT / LangChain / AutoGen / скрипты                |
+-----------------------------+----------------------------------+
                              | REST API
+-----------------------------v----------------------------------+
|                      ФРОНТЕНД                                   |
|  Vanilla JS + HTML/CSS / Phantom Wallet / Solana web3.js        |
|  /hub  /demo  /dashboard  /deploy                               |
+-----------------------------+----------------------------------+
                              |
+-----------------------------v----------------------------------+
|                   БЭКЕНД (FastAPI)                              |
|                                                                  |
|  AI Координатор (Claude)     Celery + Redis                      |
|  +-- route_task()            +-- Agent sandbox (subprocess)      |
|  +-- evaluate_output()       +-- SSE streaming логи              |
|                                                                  |
|  Роутеры: auth / agents / executions / hub / a2a / keys / open   |
+-------+-----------------------------------------+--------------+
        | solders (Python)                        |
+-------v-------------------+   +-----------------v--------------+
|   SOLANA (Devnet)         |   |      ИНФРАСТРУКТУРА            |
|   Anchor agent_escrow     |   |  Supabase / Redis / Docker     |
|   +-- AgentAccount PDA    |   |  Nginx + SSL / DigitalOcean    |
|   +-- ExecutionAccount    |   +--------------------------------+
+---------------------------+
```

---

## Стек технологий

| Слой | Технология |
|------|-----------|
| Смарт-контракт | Anchor 0.30 (Rust) на Solana Devnet |
| Бэкенд | FastAPI + Python 3.11 + async SQLAlchemy |
| AI Координатор | Claude API (`claude-sonnet-4-6`) |
| База данных | Supabase (Postgres + Storage) |
| Очередь задач | Celery + Redis |
| Фронтенд | Vanilla JS + HTML/CSS |
| Solana клиент | `solders` (Python) + `@solana/web3.js` |
| Авторизация | JWT + Phantom Wallet (Ed25519) + GitHub OAuth |
| Деплой | Docker Compose + Nginx + DigitalOcean |

---

## Соответствие критериям хакатона

**Case 2: AI + Blockchain — Autonomous Smart Contracts**

| Требование | Как закрываем |
|------------|---------------|
| AI участвует в принятии решений | Claude роутит задачи и оценивает качество результата |
| Решения меняют on-chain состояние | Оценка качества запускает complete/refund инструкции Anchor |
| Система работает автономно | A2A цепочки + AI координатор без участия человека |
| Задеплоенный смарт-контракт | Anchor программа `agent_escrow` на Solana Devnet |
| Real-world сценарий | Живой экономический маркетплейс с реальными SOL платежами |
| Открытая инфраструктура | Любой внешний AI-агент может подключиться через REST API |

---

## Быстрый старт

```bash
git clone https://github.com/unsaiddream/decentrathon5.0.git
cd decentrathon5.0
cp .env.example .env
# Заполни .env (Supabase, Solana, Anthropic, Redis)
docker compose up -d
docker compose exec api alembic upgrade head
docker compose exec api python seed_agents.py
```

| URL | Сервис |
|-----|--------|
| http://localhost:8001 | Фронтенд + API |
| http://localhost:8001/demo | Интерактивное демо |
| http://localhost:5555 | Celery Flower |

---

## Ссылки

- **Live**: [hivemind.cv](https://hivemind.cv)
- **Demo**: [hivemind.cv/demo](https://hivemind.cv/demo)
- **Solana Explorer**: [Program ID](https://explorer.solana.com/address/7dnUyWpJ2JNbCWNRjy5paJXq8bYD5QPpwe6tf1ZAGGaY?cluster=devnet)
- English version: `README.md`
- Архитектура: `CLAUDE.md`
- Задание хакатона: `task(case2).pdf`
