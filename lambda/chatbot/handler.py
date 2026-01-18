"""
AWS Lambda handler for chatbot requests.
Returns complete response (non-streaming).

"""
import json
import asyncio
import time
import re
from agents import Runner
from nutritional_agents.orchestrator import orchestrator_agent
from utils.supabase_client import supabase_client

# UUID validation pattern
UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE
)

def is_valid_uuid(value: str) -> bool:
    """Validate that a string is a valid UUID format."""
    if not value or not isinstance(value, str):
        return False
    return bool(UUID_PATTERN.match(value))


def handler(event: dict, context) -> dict:
    """
    AWS Lambda handler for chatbot requests.
    Returns complete response (non-streaming).
    """
    # Handle CORS preflight
    if event.get("httpMethod") == "OPTIONS":
        return response(200, {})
    
    try:
        # Parse request
        body = json.loads(event.get("body", "{}"))
        message = body.get("message", "")
        session_id = body.get("session_id")

        if not message:
            return response(400, {"error": "El mensaje es requerido"})

        # Validate session_id format if provided
        if session_id and not is_valid_uuid(session_id):
            return response(400, {"error": "ID de sesión inválido"})

        # Run async handler
        result = asyncio.run(process_message(message, session_id))
        
        return response(200, result)

    except Exception as e:
        print(f"Error processing request: {e}")
        return response(500, {"error": "Error interno del servidor"})


async def process_message(message: str, session_id: str = None) -> dict:
    """Process a chat message and return response."""
    supabase = supabase_client  # Use singleton instead of creating new instance
    start_time = time.time()
    success = True
    error_message = None

    try:
        # Get or create session (parallelized with get_messages when session exists)
        if session_id:
            # Parallel: get_session + get_messages
            session_task = asyncio.to_thread(supabase.get_session, session_id)
            messages_task = asyncio.to_thread(supabase.get_messages, session_id, 20, True)
            session, conversation_history = await asyncio.gather(session_task, messages_task)

            if not session:
                return {"error": "Sesión no encontrada", "session_id": None}
        else:
            # New session - create first, then get empty history
            title = message[:50] + "..." if len(message) > 50 else message
            session = await asyncio.to_thread(supabase.create_session, title=title)
            conversation_history = []

        session_id = session["id"]
        print(f"Using session ID: {session_id}")

        # Save user message in parallel with agent execution (fire and forget)
        save_user_msg_task = asyncio.create_task(asyncio.to_thread(
            supabase.save_message,
            session_id=session_id,
            role="user",
            content=message,
        ))

        # Run the agent (user message saves in parallel)
        result = await Runner.run(
            orchestrator_agent,
            input=conversation_history + [{"role": "user", "content": message}],  # Full context
            context={
                "session_id": session_id,
                "supabase": supabase,
            },
        )

        # Ensure user message is saved before continuing
        await save_user_msg_task

        response_text = result.final_output

        agent_used = "OrchestratorAgent"
        if hasattr(result, 'last_agent') and result.last_agent:
            agent_used = getattr(result.last_agent, 'name', str(result.last_agent))
            print(f"Successfully used agent: {agent_used}")

        # Calculate response time
        response_time_ms = (time.time() - start_time) * 1000

        # Save assistant response (async for faster response)
        asyncio.create_task(asyncio.to_thread(
            supabase.save_message,
            session_id=session_id,
            role="assistant",
            content=response_text,
            agent_used=agent_used
        ))

        # Save analytics in background (non-blocking for faster response)
        asyncio.create_task(asyncio.to_thread(
            supabase.save_agent_analytics,
            session_id=session_id,
            agent_name=agent_used,
            response_time_ms=response_time_ms,
            success=True,
        ))

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

        # Save error analytics in background
        if session_id:
            asyncio.create_task(asyncio.to_thread(
                supabase.save_agent_analytics,
                session_id=session_id,
                agent_name="OrchestratorAgent",
                response_time_ms=response_time_ms,
                success=False,
                error_message=error_message,
            ))

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