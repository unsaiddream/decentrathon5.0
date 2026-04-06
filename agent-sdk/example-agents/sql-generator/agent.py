#!/usr/bin/env python3
"""
SQL Generator Agent
Converts natural language questions into SQL queries.

stdin  -> {"text": "Get all users registered in the last 30 days"}
stdout -> {"sql": "SELECT ...", "explanation": "...", "dialect": "postgresql"}
"""
import sys
import json
import os
import re


def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON input: {e}"}))
        sys.exit(1)

    text = input_data.get("text", "") or input_data.get("question", "")
    if not text:
        print(json.dumps({"error": "text or question field is required"}))
        sys.exit(1)

    dialect = input_data.get("dialect", "postgresql")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        # Fallback: pattern-based SQL generation
        q = text.lower()
        table = "users"

        # Detect table from keywords
        if any(w in q for w in ["order", "purchase", "buy"]):
            table = "orders"
        elif any(w in q for w in ["product", "item", "catalog"]):
            table = "products"
        elif any(w in q for w in ["payment", "transaction", "invoice"]):
            table = "payments"

        # Build query
        if any(w in q for w in ["count", "how many", "total number"]):
            sql = f"SELECT COUNT(*) FROM {table}"
        elif any(w in q for w in ["average", "avg", "mean"]):
            sql = f"SELECT AVG(amount) FROM {table}"
        else:
            sql = f"SELECT * FROM {table}"

        # Add WHERE clauses
        conditions = []
        if "last 30 days" in q or "last month" in q:
            conditions.append("created_at >= NOW() - INTERVAL '30 days'")
        elif "last 7 days" in q or "last week" in q:
            conditions.append("created_at >= NOW() - INTERVAL '7 days'")
        elif "today" in q:
            conditions.append("created_at >= CURRENT_DATE")
        elif "this year" in q:
            conditions.append("EXTRACT(YEAR FROM created_at) = EXTRACT(YEAR FROM NOW())")

        if "active" in q:
            conditions.append("is_active = true")
        if "email" in q and "verified" in q:
            conditions.append("email_verified = true")

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        # Add ORDER/LIMIT
        if "recent" in q or "latest" in q or "newest" in q:
            sql += " ORDER BY created_at DESC"
        if "top" in q:
            match = re.search(r'top\s+(\d+)', q)
            n = match.group(1) if match else "10"
            sql += f" LIMIT {n}"

        sql += ";"

        print(json.dumps({
            "sql": sql,
            "explanation": f"Query to {text.lower().strip('.')}",
            "dialect": dialect,
            "tables_referenced": [table],
        }))
        return

    import anthropic

    prompt = f"""Convert this natural language question into an optimized SQL query ({dialect}).

Return ONLY valid JSON:
{{"sql": "the SQL query", "explanation": "brief explanation", "dialect": "{dialect}", "tables_referenced": ["table1"]}}

Question: {text}"""

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
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
