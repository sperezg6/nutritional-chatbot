"""
FastAPI streaming handler for chatbot using AWS Lambda Web Adapter.
Streams responses from OpenAI Agents SDK in real-time.
"""
import json
import time
import threading
from typing import AsyncGenerator
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agents import Runner
from nutritional_agents.orchestrator import orchestrator_agent
from utils.supabase_client import SupabaseClient


app = FastAPI(title="Nutritional Chatbot Streaming API")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


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
        supabase = SupabaseClient()
        start_time = time.time()
        session_id = request.session_id
        agent_used = "OrchestratorAgent"
        accumulated_response = ""
        success = True
        error_message = None

        try:
            # Get or create session
            if session_id:
                session = supabase.get_session(session_id)
                if not session:
                    yield f"data: {json.dumps({'type': 'error', 'content': 'Sesión no encontrada'})}\n\n"
                    return
            else:
                # Create new session
                title = request.message[:50] + "..." if len(request.message) > 50 else request.message
                session = supabase.create_session(title=title)
                session_id = session["id"]

            # Send session info
            yield f"data: {json.dumps({'type': 'start', 'session_id': session_id, 'title': session.get('title')})}\n\n"

            # Get conversation history
            conversation_history = supabase.get_messages(session_id, limit=12, for_openai=True)

            # Save user message
            supabase.save_message(
                session_id=session_id,
                role="user",
                content=request.message,
            )

            # Stream the agent response
            async for chunk in Runner.run_streamed(
                orchestrator_agent,
                input=conversation_history + [{"role": "user", "content": request.message}],
                context={
                    "session_id": session_id,
                    "supabase": supabase,
                },
            ):
                # Check if this is a text delta from the agent
                if hasattr(chunk, 'snapshot') and hasattr(chunk.snapshot, 'content'):
                    # Get the latest content
                    content = chunk.snapshot.content
                    if isinstance(content, list) and len(content) > 0:
                        # Get the text from the last message
                        last_item = content[-1]
                        if hasattr(last_item, 'text'):
                            current_text = last_item.text

                            # Send only the new delta (difference from accumulated)
                            if current_text.startswith(accumulated_response):
                                delta = current_text[len(accumulated_response):]
                                if delta:
                                    accumulated_response = current_text
                                    yield f"data: {json.dumps({'type': 'chunk', 'content': delta})}\n\n"

                # Track which agent was used
                if hasattr(chunk, 'last_agent') and chunk.last_agent:
                    agent_used = getattr(chunk.last_agent, 'name', str(chunk.last_agent))

            # Use accumulated response as final output
            response_text = accumulated_response

            if not response_text:
                # Fallback: if streaming didn't work, get the final result
                result = await Runner.run(
                    orchestrator_agent,
                    input=conversation_history + [{"role": "user", "content": request.message}],
                    context={
                        "session_id": session_id,
                        "supabase": supabase,
                    },
                )
                response_text = result.final_output
                yield f"data: {json.dumps({'type': 'chunk', 'content': response_text})}\n\n"

            # Calculate response time
            response_time_ms = (time.time() - start_time) * 1000

            # Save assistant response
            supabase.save_message(
                session_id=session_id,
                role="assistant",
                content=response_text,
                agent_used=agent_used
            )

            # Save analytics asynchronously
            def save_analytics_async():
                try:
                    supabase.save_agent_analytics(
                        session_id=session_id,
                        agent_name=agent_used,
                        response_time_ms=response_time_ms,
                        success=True,
                    )
                except Exception as e:
                    print(f"Background analytics save failed: {e}")

            threading.Thread(target=save_analytics_async, daemon=True).start()

            # Send completion event
            yield f"data: {json.dumps({'type': 'end', 'agent_used': agent_used})}\n\n"

        except Exception as e:
            success = False
            error_message = str(e)
            print(f"Error in streaming: {e}")

            # Calculate response time even on error
            response_time_ms = (time.time() - start_time) * 1000

            # Save error analytics
            if session_id:
                def save_error_analytics_async():
                    try:
                        supabase.save_agent_analytics(
                            session_id=session_id,
                            agent_name=agent_used,
                            response_time_ms=response_time_ms,
                            success=False,
                            error_message=error_message,
                        )
                    except Exception as analytics_error:
                        print(f"Failed to save error analytics: {analytics_error}")

                threading.Thread(target=save_error_analytics_async, daemon=True).start()

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
