"""
AWS Lambda handler for chatbot requests.
Returns complete response (non-streaming).

"""
import json
import asyncio
import os
import time
import threading
from agents import Runner
from nutritional_agents.orchestrator import orchestrator_agent
from utils.supabase_client import SupabaseClient


def handler(event: dict, context) -> dict:
    """
    AWS Lambda handler for chatbot requests.
    Returns complete response (non-streaming).
    Supports both API Gateway and Lambda Function URL event formats.
    """
    # Detect request method (API Gateway vs Function URL format)
    http_method = event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method")

    # Handle CORS preflight
    if http_method == "OPTIONS":
        return response(200, {})

    try:
        # Parse request body
        raw_body = event.get("body", "{}")
        # Function URLs may base64 encode the body
        if event.get("isBase64Encoded"):
            import base64
            raw_body = base64.b64decode(raw_body).decode("utf-8")
        body = json.loads(raw_body)
        message = body.get("message", "")
        session_id = body.get("session_id")

        if not message:
            return response(400, {"error": "El mensaje es requerido"})

        # Run async handler
        result = asyncio.run(process_message(message, session_id))
        
        return response(200, result)

    except Exception as e:
        print(f"Error processing request: {e}")
        return response(500, {"error": "Error interno del servidor"})


async def process_message(message: str, session_id: str = None) -> dict:
    """Process a chat message and return response."""

    supabase = SupabaseClient()
    start_time = time.time()
    success = True
    error_message = None

    try:
        # Get or create session
        if session_id:
            session = supabase.get_session(session_id)
            if not session:
                return {"error": "Sesión no encontrada", "session_id": None}
        else:
            # Extract title from first message (without fallback)
            title = message[:50] + "..." if len(message) > 50 else message
            session = supabase.create_session(title=title)

        session_id = session["id"]
        print(f"Using session ID: {session_id}")

        conversation_history = supabase.get_messages(session_id, limit=12, for_openai=True)

        #  Save user message
        supabase.save_message(
            session_id=session_id,
            role="user",
            content=message,
        )

        # Run the agent
        result = await Runner.run(
            orchestrator_agent,
            input=conversation_history + [{"role": "user", "content": message}],  # Full context
            context={
                "session_id": session_id,
                "supabase": supabase,
            },
        )

        response_text = result.final_output

        agent_used = "OrchestratorAgent"
        if hasattr(result, 'last_agent') and result.last_agent:
            agent_used = getattr(result.last_agent, 'name', str(result.last_agent))
            print(f"Successfully used agent: {agent_used}")

        # Calculate response time
        response_time_ms = (time.time() - start_time) * 1000

        # Save assistant response
        supabase.save_message(
            session_id=session_id,
            role="assistant",
            content=response_text,
            agent_used=agent_used
        )

        # Save analytics asynchronously (non-blocking for faster response)
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

        # Start analytics save in background thread
        threading.Thread(target=save_analytics_async, daemon=True).start()

        return {
            "response": response_text,
            "session_id": session_id,
            "title": session.get("title"),
        }

    except Exception as e:
        success = False
        error_message = str(e)
        print(f"Error in process_message: {e}")

        # Calculate response time even on error
        response_time_ms = (time.time() - start_time) * 1000

        # Try to save analytics even on error (async, non-blocking)
        if session_id:
            def save_error_analytics_async():
                try:
                    supabase.save_agent_analytics(
                        session_id=session_id,
                        agent_name="OrchestratorAgent",
                        response_time_ms=response_time_ms,
                        success=False,
                        error_message=error_message,
                    )
                except Exception as analytics_error:
                    print(f"Failed to save error analytics: {analytics_error}")

            threading.Thread(target=save_error_analytics_async, daemon=True).start()

        raise  # Re-raise the exception to be handled by the main handler


def response(status_code: int, body: dict) -> dict:
    """Create API Gateway response."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Session-Id",
            "Access-Control-Allow-Methods": "POST,OPTIONS",
        },
        "body": json.dumps(body, ensure_ascii=False),
    }