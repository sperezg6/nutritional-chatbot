"""
AWS Lambda handler for chatbot requests.
Returns complete response (non-streaming).

"""
import json
import asyncio
import os
from agents import Runner
from nutritional_agents.orchestrator import orchestrator_agent
from utils.supabase_client import SupabaseClient


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

        # Run async handler
        result = asyncio.run(process_message(message, session_id))
        
        return response(200, result)

    except Exception as e:
        print(f"Error processing request: {e}")
        return response(500, {"error": "Error interno del servidor"})


async def process_message(message: str, session_id: str = None) -> dict:
    """Process a chat message and return response."""
    
    supabase = SupabaseClient()

    # Get or create session
    if session_id:
        session = supabase.get_session(session_id)
        if not session:
            return {"error": "Sesión no encontrada", "session_id": None}
    else:
        session = supabase.create_session()
    
    session_id = session["id"]
    print(f"Using session ID: {session_id}")

    # Load conversation history
    conversation_history = supabase.get_messages(session_id, limit=50, for_openai=True)
    print(f"Loaded {len(conversation_history)} messages from history.")


    # Run the agent
    result = await Runner.run(
        orchestrator_agent,
        input=message,
        context={
            "session_id": session_id,
            "conversation_history": conversation_history,
            "supabase": supabase,
        },
    )

    response_text = result.final_output
    last_agent = getattr(result, "last_agent", "Orchestrator")

    # TO DO: Save conversation turn

    return {
        "response": response_text,
        "session_id": session_id,
        "agent": last_agent,
    }


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