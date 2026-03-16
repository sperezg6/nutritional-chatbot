"""
FastAPI streaming handler for chatbot using AWS Lambda Web Adapter.
Streams responses from OpenAI Agents SDK in real-time.
"""
import json
import time
import re
import asyncio
from typing import AsyncGenerator
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from agents import Runner
from nutritional_agents.orchestrator import orchestrator_agent
from nutritional_agents.safety import run_safety_check
from utils.dynamodb_client import dynamodb_client

# UUID validation pattern
UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE
)

app = FastAPI(title="Nutritional Chatbot Streaming API")

# Note: CORS is handled by Lambda Function URL configuration
# Removing duplicate CORS middleware to avoid duplicate headers


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None

    @field_validator('session_id')
    @classmethod
    def validate_session_id(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not UUID_PATTERN.match(v):
            raise ValueError('ID de sesión inválido')
        return v


class ChatChunk(BaseModel):
    type: str  # "start" | "chunk" | "end" | "error"
    content: str = ""
    session_id: str | None = None
    title: str | None = None
    agent_used: str | None = None


@app.post("/chat-stream")
async def chat_stream(request: ChatRequest):
    """
    Stream chatbot responses using Server-Sent Events (SSE).
    """

    async def generate_response() -> AsyncGenerator[str, None]:
        """Generate streaming response chunks."""
        db = dynamodb_client  # Use singleton instead of creating new instance
        start_time = time.time()
        session_id = request.session_id
        agent_used = "OrchestratorAgent"
        accumulated_response = ""
        success = True
        error_message = None

        try:
            # Get or create session (parallelized with get_messages when session exists)
            if session_id:
                # Parallel: get_session + get_messages
                session_task = asyncio.to_thread(db.get_session, session_id)
                messages_task = asyncio.to_thread(db.get_messages, session_id, 20, True)
                session, conversation_history = await asyncio.gather(session_task, messages_task)

                if not session:
                    yield f"data: {json.dumps({'type': 'error', 'content': 'Sesión no encontrada'})}\n\n"
                    return
            else:
                # Create new session
                title = request.message[:50] + "..." if len(request.message) > 50 else request.message
                session = await asyncio.to_thread(db.create_session, title=title)
                session_id = session["id"]
                conversation_history = []

            # Send session info
            yield f"data: {json.dumps({'type': 'start', 'session_id': session_id, 'title': session.get('title')})}\n\n"

            # Save user message BEFORE running agent (ensures complete history)
            await asyncio.to_thread(
                db.save_message,
                session_id=session_id,
                role="user",
                content=request.message,
            )

            # Stream the agent response
            from openai.types.responses import ResponseTextDeltaEvent

            result = Runner.run_streamed(
                orchestrator_agent,
                input=conversation_history + [{"role": "user", "content": request.message}],
            )

            # Iterate through streaming events
            async for event in result.stream_events():
                # Check for text delta events from the LLM
                if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
                    delta = event.data.delta
                    if delta:
                        accumulated_response += delta
                        yield f"data: {json.dumps({'type': 'chunk', 'content': delta})}\n\n"

            # After streaming, check if we have agent info from the result
            if hasattr(result, 'last_agent') and result.last_agent:
                agent_used = getattr(result.last_agent, 'name', str(result.last_agent))

            # Use accumulated response as final output
            response_text = accumulated_response

            if not response_text:
                print("Warning: streaming produced no output")
                response_text = "Lo siento, ocurrió un problema al generar la respuesta. Por favor intente de nuevo."
                yield f"data: {json.dumps({'type': 'chunk', 'content': response_text})}\n\n"

            # Post-process every response through safety checker
            checked_text = await run_safety_check(response_text)
            if checked_text != response_text:
                # Safety modified/blocked the response — send correction to client
                yield f"data: {json.dumps({'type': 'safety_correction', 'content': checked_text})}\n\n"
                response_text = checked_text

            # Calculate response time
            response_time_ms = (time.time() - start_time) * 1000

            # Save assistant response and analytics (awaited to avoid data loss)
            await asyncio.gather(
                asyncio.to_thread(
                    db.save_message,
                    session_id=session_id,
                    role="assistant",
                    content=response_text,
                    agent_used=agent_used,
                ),
                asyncio.to_thread(
                    db.save_agent_analytics,
                    session_id=session_id,
                    agent_name=agent_used,
                    response_time_ms=response_time_ms,
                    success=True,
                ),
            )

            # Send completion event
            yield f"data: {json.dumps({'type': 'end', 'agent_used': agent_used})}\n\n"

        except Exception as e:
            success = False
            error_message = str(e)
            print(f"Error in streaming: {e}")

            # Calculate response time even on error
            response_time_ms = (time.time() - start_time) * 1000

            # Save error analytics (awaited to avoid data loss)
            if session_id:
                try:
                    await asyncio.to_thread(
                        db.save_agent_analytics,
                        session_id=session_id,
                        agent_name=agent_used,
                        response_time_ms=response_time_ms,
                        success=False,
                        error_message=error_message,
                    )
                except Exception as analytics_err:
                    print(f"Failed to save error analytics: {analytics_err}")

            yield f"data: {json.dumps({'type': 'error', 'content': f'Error: {str(e)}'})}\n\n"

    return StreamingResponse(
        generate_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable proxy buffering
        }
    )


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "nutritional-chatbot-streaming"}
