"""Command-line interface for the agent.

Usage:
    uv run main.py                          # interactive chat
    uv run main.py --debug                  # also show which tools were called
    uv run main.py --script script.txt --save examples/conversation.md
        # run the customer messages in the script (one per line) and save the transcript
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from langchain.messages import AIMessage

from agent import build_agent

EXIT_WORDS = {"sair", "tchau", "exit", "quit"}


def tools_called(messages) -> list[str]:
    calls = []
    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                calls.append(f"{call['name']}({json.dumps(call['args'], ensure_ascii=False)})")
    return calls


def reply(agent, config, text: str) -> tuple[str, list[str]]:
    previous = len(agent.get_state(config).values.get("messages", []))
    state = agent.invoke({"messages": [{"role": "user", "content": text}]}, config)
    return state["messages"][-1].text, tools_called(state["messages"][previous:])


def main() -> None:
    parser = argparse.ArgumentParser(description="Empório da Música virtual assistant")
    parser.add_argument("--debug", action="store_true", help="show the tools called on each turn")
    parser.add_argument("--script", type=Path, help="file with one customer message per line")
    parser.add_argument("--save", type=Path, help="save the conversation as Markdown")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    agent = build_agent()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    transcript: list[str] = []

    def turn(text: str) -> None:
        answer, calls = reply(agent, config, text)
        if args.script:
            print(f"Cliente: {text}")
        if args.debug or args.script:
            for call in calls:
                print(f"  [tool] {call}")
        print(f"Toninho: {answer}\n")
        transcript.append(f"**Cliente:** {text}\n")
        transcript.extend(f"> 🔧 `{call}`\n" for call in calls)
        transcript.append(f"**Toninho:** {answer}\n")

    if args.script:
        for line in args.script.read_text(encoding="utf-8").splitlines():
            if line.strip():
                turn(line.strip())
    else:
        print("Empório da Música - assistente virtual (digite 'sair' para encerrar)\n")
        while True:
            try:
                text = input("Você: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not text:
                continue
            if text.lower() in EXIT_WORDS:
                print("Toninho: Valeu pela visita! Até a próxima. 🎸")
                break
            turn(text)

    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text("\n".join(transcript), encoding="utf-8")
        print(f"Conversation saved to {args.save}")


if __name__ == "__main__":
    main()
