import json
from typing import AsyncIterator

import httpx

DONE = "data: [DONE]\n\n"


def event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def ollama_tokens(resp: httpx.Response) -> AsyncIterator[tuple[str, list]]:
    """Consume an Ollama /api/chat JSON-line stream.

    Yields (content, tool_calls) pairs. tool_calls is non-empty only when the
    model requests a tool call; content and tool_calls are mutually exclusive in
    normal Ollama responses.
    """
    async for line in resp.aiter_lines():
        if not line:
            continue
        data = json.loads(line)
        msg = data.get("message", {})
        tool_calls = msg.get("tool_calls") or []
        content = msg.get("content", "")
        if content or tool_calls:
            yield content, tool_calls
        if data.get("done"):
            break
