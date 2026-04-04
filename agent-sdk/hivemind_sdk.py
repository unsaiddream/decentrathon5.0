"""
HiveMind SDK — Open Agent Protocol client.

Позволяет любому Python-скрипту, LangChain-агенту или AI-системе
вызывать агентов HiveMind без регистрации.

Установка:
    pip install httpx  # единственная зависимость

Использование:
    from hivemind_sdk import HiveMind

    hm = HiveMind()  # по умолчанию hivemind.cv

    # Список агентов
    agents = hm.list_agents()
    agents = hm.discover(capability="summarization")

    # Вызов агента
    result = hm.invoke("2qtxr7zo/text-summarizer", {"text": "Long document..."})
    print(result.output)            # Результат агента
    print(result.ai_quality_score)  # AI оценка 0-100
    print(result.explorer_url)      # Solana Explorer ссылка

    # Async использование (для asyncio/FastAPI проектов)
    result = await hm.ainvoke("2qtxr7zo/sentiment-analyzer", {"text": "I love Solana!"})

    # LangChain интеграция
    from hivemind_sdk import HiveMindTool
    tool = HiveMindTool("2qtxr7zo/text-summarizer")
    # tool совместим с langchain.tools.BaseTool
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class AgentInfo:
    slug: str
    name: str
    description: str
    category: str
    capabilities: list[str]
    price_per_call: str
    call_count: int
    on_chain_address: str | None
    invoke_url: str
    input_schema: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.slug} — {self.description} [{', '.join(self.capabilities)}]"


@dataclass
class InvokeResult:
    execution_id: str
    status: str
    output: dict[str, Any] | None
    error: str | None
    duration_ms: int | None
    ai_quality_score: int | None       # 0-100 from Claude
    ai_reasoning: str | None
    on_chain_execution_id: str | None
    on_chain_tx_hash: str | None
    complete_tx_hash: str | None
    explorer_url: str | None
    agent_slug: str

    def __bool__(self) -> bool:
        return self.status == "done"

    @property
    def text(self) -> str:
        """Удобный доступ к текстовому результату."""
        if not self.output:
            return self.error or ""
        return (
            self.output.get("result")
            or self.output.get("output")
            or self.output.get("text")
            or self.output.get("content")
            or json.dumps(self.output)
        )

    def __str__(self) -> str:
        score_str = f" | AI:{self.ai_quality_score}/100" if self.ai_quality_score is not None else ""
        chain_str = f" | ⛓ {self.explorer_url}" if self.explorer_url else ""
        return f"[{self.status}{score_str}{chain_str}] {self.text[:200]}"


# ─── Main client ──────────────────────────────────────────────────────────────

class HiveMind:
    """
    HiveMind Open Agent Protocol client.

    Любой агент, инструмент или система может вызывать агентов
    децентрализованного маркетплейса HiveMind.
    """

    def __init__(
        self,
        base_url: str = "https://hivemind.cv",
        caller_system: str = "hivemind-sdk",
        timeout: float = 120.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.caller_system = caller_system
        self.timeout = timeout

    # ── Discovery ──────────────────────────────────────────────────────────────

    def list_agents(self, category: str | None = None, limit: int = 50) -> list[AgentInfo]:
        """Список всех публичных агентов."""
        return asyncio.get_event_loop().run_until_complete(
            self.alist_agents(category=category, limit=limit)
        )

    async def alist_agents(self, category: str | None = None, limit: int = 50) -> list[AgentInfo]:
        import httpx
        params = {"limit": limit}
        if category:
            params["category"] = category
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.base_url}/open/agents", params=params)
            resp.raise_for_status()
            data = resp.json()
        return [self._parse_agent(a) for a in data.get("agents", [])]

    def discover(
        self,
        capability: str | None = None,
        query: str | None = None,
        limit: int = 20,
    ) -> list[AgentInfo]:
        """Поиск агентов по capability или запросу."""
        return asyncio.get_event_loop().run_until_complete(
            self.adiscover(capability=capability, query=query, limit=limit)
        )

    async def adiscover(
        self,
        capability: str | None = None,
        query: str | None = None,
        limit: int = 20,
    ) -> list[AgentInfo]:
        import httpx
        params = {"limit": limit}
        if capability:
            params["capability"] = capability
        if query:
            params["query"] = query
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.base_url}/open/discover", params=params)
            resp.raise_for_status()
            data = resp.json()
        return [self._parse_agent(a) for a in data]

    def get_agent(self, slug: str) -> AgentInfo:
        """Детали агента по slug."""
        return asyncio.get_event_loop().run_until_complete(self.aget_agent(slug))

    async def aget_agent(self, slug: str) -> AgentInfo:
        import httpx
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.base_url}/open/agents/{slug}")
            if resp.status_code == 404:
                raise ValueError(f"Agent '{slug}' not found")
            resp.raise_for_status()
        return self._parse_agent(resp.json())

    # ── Invocation ─────────────────────────────────────────────────────────────

    def invoke(
        self,
        slug: str,
        input_data: dict[str, Any],
        caller_id: str | None = None,
    ) -> InvokeResult:
        """
        Синхронный вызов агента.

        Пример:
            result = hm.invoke("2qtxr7zo/text-summarizer", {"text": "..."})
            print(result.text)
        """
        return asyncio.get_event_loop().run_until_complete(
            self.ainvoke(slug, input_data, caller_id=caller_id)
        )

    async def ainvoke(
        self,
        slug: str,
        input_data: dict[str, Any],
        caller_id: str | None = None,
    ) -> InvokeResult:
        """Async вызов агента."""
        import httpx
        payload = {
            "input": input_data,
            "caller_system": self.caller_system,
        }
        if caller_id:
            payload["caller_id"] = caller_id

        headers = {
            "X-Caller-System": self.caller_system,
            "Content-Type": "application/json",
        }
        if caller_id:
            headers["X-Caller-Agent"] = caller_id

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/open/invoke/{slug}",
                json=payload,
                headers=headers,
            )
            if resp.status_code == 404:
                raise ValueError(f"Agent '{slug}' not found")
            resp.raise_for_status()
            data = resp.json()

        return self._parse_result(data)

    def invoke_pipeline(
        self,
        slugs: list[str],
        initial_input: dict[str, Any],
    ) -> list[InvokeResult]:
        """
        Последовательный вызов нескольких агентов (pipeline).
        Вывод каждого агента становится входом следующего.

        Пример:
            results = hm.invoke_pipeline(
                ["2qtxr7zo/text-summarizer", "2qtxr7zo/sentiment-analyzer"],
                {"text": "Long article..."}
            )
        """
        return asyncio.get_event_loop().run_until_complete(
            self.ainvoke_pipeline(slugs, initial_input)
        )

    async def ainvoke_pipeline(
        self,
        slugs: list[str],
        initial_input: dict[str, Any],
    ) -> list[InvokeResult]:
        results = []
        current_input = initial_input

        for slug in slugs:
            result = await self.ainvoke(slug, current_input)
            results.append(result)

            if not result or not result.output:
                break  # pipeline прерывается при ошибке

            # Вывод текущего шага становится входом следующего
            current_input = result.output

        return results

    # ── Solana Discovery ───────────────────────────────────────────────────────

    def get_program_info(self) -> dict:
        """Информация о Solana программе для on-chain верификации."""
        return asyncio.get_event_loop().run_until_complete(self._aget_program_info())

    async def _aget_program_info(self) -> dict:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.base_url}/open/program")
            resp.raise_for_status()
        return resp.json()

    # ── Parsers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_agent(data: dict) -> AgentInfo:
        return AgentInfo(
            slug=data["slug"],
            name=data["name"],
            description=data.get("description") or "",
            category=data.get("category") or "",
            capabilities=data.get("capabilities") or [],
            price_per_call=data.get("price_per_call", "0"),
            call_count=data.get("call_count", 0),
            on_chain_address=data.get("on_chain_address"),
            invoke_url=data.get("invoke_url", ""),
            input_schema=data.get("input_schema") or {},
        )

    @staticmethod
    def _parse_result(data: dict) -> InvokeResult:
        return InvokeResult(
            execution_id=data["execution_id"],
            status=data["status"],
            output=data.get("output"),
            error=data.get("error"),
            duration_ms=data.get("duration_ms"),
            ai_quality_score=data.get("ai_quality_score"),
            ai_reasoning=data.get("ai_reasoning"),
            on_chain_execution_id=data.get("on_chain_execution_id"),
            on_chain_tx_hash=data.get("on_chain_tx_hash"),
            complete_tx_hash=data.get("complete_tx_hash"),
            explorer_url=data.get("explorer_url"),
            agent_slug=data.get("agent_slug", ""),
        )


# ─── LangChain Tool adapter ────────────────────────────────────────────────────

class HiveMindTool:
    """
    LangChain-совместимый инструмент для HiveMind агентов.

    Использование с LangChain:
        from hivemind_sdk import HiveMindTool
        from langchain.agents import initialize_agent, AgentType
        from langchain.llms import OpenAI

        tools = [
            HiveMindTool("2qtxr7zo/text-summarizer"),
            HiveMindTool("2qtxr7zo/sentiment-analyzer"),
        ]
        agent = initialize_agent(tools, OpenAI(), agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION)
        agent.run("Summarize and analyze: 'I love blockchain technology!'")
    """

    def __init__(self, slug: str, base_url: str = "https://hivemind.cv"):
        self.slug = slug
        self._client = HiveMind(base_url=base_url, caller_system="langchain")
        self._agent_info: AgentInfo | None = None

    @property
    def name(self) -> str:
        slug_short = self.slug.split("/")[-1] if "/" in self.slug else self.slug
        return f"hivemind_{slug_short.replace('-', '_')}"

    @property
    def description(self) -> str:
        if self._agent_info:
            caps = ", ".join(self._agent_info.capabilities)
            return f"{self._agent_info.description}. Capabilities: {caps}"
        return f"HiveMind agent: {self.slug}"

    def _run(self, input_text: str) -> str:
        """LangChain sync tool call."""
        result = self._client.invoke(self.slug, {"text": input_text})
        return result.text

    async def _arun(self, input_text: str) -> str:
        """LangChain async tool call."""
        result = await self._client.ainvoke(self.slug, {"text": input_text})
        return result.text

    def load_info(self) -> "HiveMindTool":
        """Загружает метаданные агента для улучшения description."""
        try:
            self._agent_info = self._client.get_agent(self.slug)
        except Exception:
            pass
        return self


# ─── MCP (Model Context Protocol) Server ──────────────────────────────────────

class HiveMindMCPServer:
    """
    MCP Server — делает агентов HiveMind доступными как tools
    для Claude Desktop, Cursor, и любого MCP-совместимого клиента.

    Запуск:
        python hivemind_sdk.py --mcp

    Конфигурация Claude Desktop (~/.config/claude/claude_desktop_config.json):
        {
          "mcpServers": {
            "hivemind": {
              "command": "python",
              "args": ["/path/to/hivemind_sdk.py", "--mcp"],
              "env": {"HIVEMIND_URL": "https://hivemind.cv"}
            }
          }
        }
    """

    def __init__(self, base_url: str = "https://hivemind.cv"):
        self._client = HiveMind(base_url=base_url, caller_system="mcp")
        self._agents: list[AgentInfo] = []

    def _refresh_agents(self):
        try:
            self._agents = self._client.list_agents()
        except Exception as e:
            import sys
            print(f"Warning: could not load agents: {e}", file=sys.stderr)

    def run(self):
        """Запускает MCP сервер на stdio."""
        import sys

        self._refresh_agents()

        # MCP protocol over stdio
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                response = self._handle(msg)
                print(json.dumps(response), flush=True)
            except Exception as e:
                print(json.dumps({"error": str(e)}), flush=True)

    def _handle(self, msg: dict) -> dict:
        method = msg.get("method", "")
        msg_id = msg.get("id")

        if method == "initialize":
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "hivemind", "version": "1.0.0"},
                }
            }

        if method == "tools/list":
            tools = []
            for agent in self._agents:
                schema = agent.input_schema or {"type": "object", "properties": {"text": {"type": "string"}}}
                tools.append({
                    "name": f"hivemind_{agent.slug.replace('/', '__').replace('-', '_')}",
                    "description": f"{agent.description} [HiveMind: {agent.slug}] | Price: {agent.price_per_call} SOL | On-chain: {bool(agent.on_chain_address)}",
                    "inputSchema": schema,
                })
            # Добавляем meta-tools
            tools.append({
                "name": "hivemind_discover",
                "description": "Discover HiveMind agents by capability or text query",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "capability": {"type": "string", "description": "e.g. summarization, sentiment, translation"},
                        "query": {"type": "string", "description": "Free-text search"},
                    }
                }
            })
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools}}

        if method == "tools/call":
            name = msg.get("params", {}).get("name", "")
            arguments = msg.get("params", {}).get("arguments", {})

            if name == "hivemind_discover":
                agents = self._client.discover(
                    capability=arguments.get("capability"),
                    query=arguments.get("query"),
                )
                text = "\n".join(str(a) for a in agents) or "No agents found"
                return {
                    "jsonrpc": "2.0", "id": msg_id,
                    "result": {"content": [{"type": "text", "text": text}]}
                }

            # Находим агента по имени инструмента
            slug = name.replace("hivemind_", "").replace("__", "/").replace("_", "-")
            # Пробуем точное совпадение
            agent = next((a for a in self._agents if a.slug == slug or a.slug.replace("/", "__").replace("-", "_") in name), None)
            if not agent:
                return {
                    "jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": -32601, "message": f"Tool not found: {name}"}
                }

            result = self._client.invoke(agent.slug, arguments)
            content = result.text
            if result.ai_quality_score is not None:
                content += f"\n\n[AI Quality Score: {result.ai_quality_score}/100]"
            if result.explorer_url:
                content += f"\n[Solana TX: {result.explorer_url}]"

            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {"content": [{"type": "text", "text": content}]}
            }

        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import os

    base_url = os.environ.get("HIVEMIND_URL", "https://hivemind.cv")

    if "--mcp" in sys.argv:
        # Режим MCP сервера
        server = HiveMindMCPServer(base_url=base_url)
        server.run()
        sys.exit(0)

    if len(sys.argv) < 2:
        print("HiveMind SDK CLI")
        print()
        print("Usage:")
        print("  python hivemind_sdk.py list                          — list agents")
        print("  python hivemind_sdk.py discover --cap summarization  — discover by capability")
        print("  python hivemind_sdk.py invoke <slug> <json_input>    — call agent")
        print("  python hivemind_sdk.py --mcp                         — run as MCP server")
        print()
        print(f"API: {base_url}/open/agents")
        sys.exit(0)

    hm = HiveMind(base_url=base_url)
    cmd = sys.argv[1]

    if cmd == "list":
        agents = hm.list_agents()
        print(f"{'Slug':<45} {'Capabilities':<30} {'Price':<10} {'On-chain'}")
        print("-" * 100)
        for a in agents:
            caps = ", ".join(a.capabilities[:2])
            chain = "✓" if a.on_chain_address else "✗"
            print(f"{a.slug:<45} {caps:<30} {a.price_per_call:<10} {chain}")

    elif cmd == "discover":
        cap = next((sys.argv[i+1] for i, a in enumerate(sys.argv) if a in ("--cap", "--capability") and i+1 < len(sys.argv)), None)
        q = next((sys.argv[i+1] for i, a in enumerate(sys.argv) if a == "--query" and i+1 < len(sys.argv)), None)
        agents = hm.discover(capability=cap, query=q)
        for a in agents:
            print(f"  {a.slug}: {a.description}")
            if a.capabilities:
                print(f"    capabilities: {', '.join(a.capabilities)}")
            if a.on_chain_address:
                print(f"    on-chain PDA: {a.on_chain_address}")
            print()

    elif cmd == "invoke":
        if len(sys.argv) < 4:
            print("Usage: python hivemind_sdk.py invoke <slug> '<json_input>'")
            print('Example: python hivemind_sdk.py invoke 2qtxr7zo/text-summarizer \'{"text": "Hello world"}\'')
            sys.exit(1)
        slug = sys.argv[2]
        input_json = json.loads(sys.argv[3])
        print(f"Invoking {slug}...")
        result = hm.invoke(slug, input_json)
        print(f"\nStatus: {result.status}")
        if result.ai_quality_score is not None:
            verdict = "✓ Approved" if result.ai_quality_score >= 70 else "✗ Refunded"
            print(f"AI Score: {result.ai_quality_score}/100 ({verdict})")
            if result.ai_reasoning:
                print(f"Reasoning: {result.ai_reasoning}")
        if result.explorer_url:
            print(f"Solana TX: {result.explorer_url}")
        if result.duration_ms:
            print(f"Duration: {result.duration_ms}ms")
        print(f"\nOutput:")
        print(result.text)

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
