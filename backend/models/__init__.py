# Импортируем все модели чтобы alembic их видел при autogenerate
from .user import User
from .agent import Agent
from .execution import Execution
from .transaction import Transaction
from .rating import Rating
from .agent_message import AgentMessage
from .api_key import ApiKey

__all__ = ["User", "Agent", "Execution", "Transaction", "Rating", "AgentMessage", "ApiKey"]
