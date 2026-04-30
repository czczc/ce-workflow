import json

import httpx

from config import settings

MONITOR_SYSTEM_PROMPT = (
    "You are the Monitor Agent in a cold electronics QA/QC workflow. "
    "Your job is to gate the start of QC testing based on the hardware anomaly detection result. "
    "If hardware is good, confirm the check passed and state that QC testing is starting. "
    "If a defect is detected, clearly describe the finding and instruct the operator to fix it before proceeding."
)


async def run_monitor_agent():
    yield f"data: {json.dumps({'type': 'token', 'text': '*Checking hardware status...*\n\n'})}\n\n"

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(settings.hardware_check_url)
            resp.raise_for_status()
            result = resp.json()
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'token', 'text': f'**Error contacting hardware anomaly detection service:** {exc}\n'})}\n\n"
            yield "data: [DONE]\n\n"
            return

    status = result.get("status", "unknown")
    detail = result.get("detail", "")

    user_content = (
        f"Hardware anomaly detection result:\n```json\n{json.dumps(result, indent=2)}\n```\n\n"
        "Provide your assessment and next step."
    )

    messages = [
        {"role": "system", "content": MONITOR_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.reasoning_model,
                "messages": messages,
                "stream": True,
                "think": False,
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                data = json.loads(line)
                token = data.get("message", {}).get("content", "")
                if token:
                    yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"
                if data.get("done"):
                    break

    yield "data: [DONE]\n\n"
