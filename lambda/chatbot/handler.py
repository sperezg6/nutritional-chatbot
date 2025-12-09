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
    
    # Build input with history context
    if conversation_history:
        # Add history to the message so the agent knows the context
        history_text = "\n".join([
            f"{'Usuario' if m['role'] == 'user' else 'Asistente'}: {m['content']}"
            for m in conversation_history[-6:]  # Last 6 messages
        ])
        full_input = f"[Historial reciente]\n{history_text}\n\n[Mensaje actual]\n{message}"
    else:
        full_input = message

    print(f"Full input to agent:\n{full_input}")


    # Run the agent (no complex objects in context)
    result = await Runner.run(
        orchestrator_agent,
        input=full_input,
    )

    response_text = result.final_output

    # TO DO: Save conversation turn

    return {
        "response": response_text,
        "session_id": session_id,
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