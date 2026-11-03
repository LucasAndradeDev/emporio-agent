"""Agent graph (LangGraph).

    START -> agent --(tool_calls?)--> tools -> agent
                   \\--(no)--> END

The graph is built by hand (instead of using a prebuilt agent) to make the reasoning
loop explicit: the LLM decides whether it needs a tool, the ToolNode runs it, and the
result goes back to the LLM until it answers the customer without requesting tools.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from google.genai.errors import APIError
from langchain.messages import SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import RetryPolicy

from prompts import build_system_prompt
from tools import TOOLS

load_dotenv()

DEFAULT_MODEL = "gemini-3.5-flash"


def _is_transient_error(error: Exception) -> bool:
    """The free tier sometimes returns 403/429/503 for a moment under load.

    A 429 caused by the *daily* quota is not transient (it only resets the next day),
    so it is not retried.
    """
    cause = error.__cause__ or error
    if not isinstance(cause, APIError) or cause.code not in {403, 429, 500, 503}:
        return False
    return not (cause.code == 429 and "PerDay" in str(cause))


def build_agent(checkpointer=None):
    llm = ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL") or DEFAULT_MODEL,
        temperature=0.3,  # low: consistent answers without sounding robotic
    )
    llm_with_tools = llm.bind_tools(TOOLS)

    def agent(state: MessagesState):
        # The system prompt is rebuilt on every turn so it carries the current date/time.
        messages = [SystemMessage(build_system_prompt())] + state["messages"]
        return {"messages": [llm_with_tools.invoke(messages)]}

    graph = StateGraph(MessagesState)
    graph.add_node(
        "agent",
        agent,
        retry_policy=RetryPolicy(max_attempts=4, initial_interval=2.0, retry_on=_is_transient_error),
    )
    graph.add_node("tools", ToolNode(TOOLS))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)  # -> "tools" or END
    graph.add_edge("tools", "agent")

    # The checkpointer stores the history per thread_id: each conversation has its own memory.
    return graph.compile(checkpointer=checkpointer or InMemorySaver())


if __name__ == "__main__":
    print(build_agent().get_graph().draw_mermaid())
