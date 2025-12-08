"""
Supabase client for Kidney Nutrition Chatbot
Session-first approach (no users for MVP)
"""
import os
from typing import Optional
from datetime import datetime, date
from supabase import create_client, Client


class SupabaseClient:
    """Supabase client wrapper."""

    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")

        self.client: Client = create_client(url, key)

    
    # ===== SESSIONS =====
    def create_session(self, metadata: dict = None) -> dict:
        """
        Create a new chat session.
        
        Args:
            metadata: Optional metadata (source, device, etc.)
        
        Returns:
            Created session record
        """
        data = {
            "patient_context": {},
            "metadata": metadata or {},
            "is_active": True,
        }
        
        response = self.client.table("sessions").insert(data).execute()
        return response.data[0] if response.data else None
    
    def get_session(self, session_id: str) -> Optional[dict]:   
        """
        Get session by ID.
        
        Args:
            session_id: Session ID
        
        Returns:
            Session record or None
        """
        """
        Get a session by ID.
        
        Args:
            session_id: UUID of the session
        
        Returns:
            Session record or None
        """
        try:
            response = self.client.table("sessions") \
                .select("*") \
                .eq("id", session_id) \
                .single() \
                .execute()
            return response.data
        except Exception:
            return None
        

    def end_session(self, session_id: str) -> dict:
        """Mark a session as inactive."""
        response = self.client.table("sessions") \
            .update({"is_active": False}) \
            .eq("id", session_id) \
            .execute()
        
        return response.data[0] if response.data else None
    
    
    # ==================== Messages ====================
    def get_messages(
        self, 
        session_id: str, 
        limit: int = 20,
        for_openai: bool = True,
    ) -> list[dict]:
        """
        Get conversation history for a session.
        
        Args:
            session_id: UUID of the session
            limit: Maximum messages to return
            for_openai: If True, format for OpenAI messages array
        
        Returns:
            List of messages (oldest first)
        """
        response = self.client.table("messages") \
            .select("*") \
            .eq("session_id", session_id) \
            .order("sequence_number", desc=False) \
            .limit(limit) \
            .execute()
        
        messages = response.data or []
        
        if for_openai:
            return [
                {"role": msg["role"], "content": msg["content"]}
                for msg in messages
            ]
        
        return messages

    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        agent_used: str = None,
        tool_calls: dict = None,
    ) -> dict:
        """
        Save a message to the conversation.
        
        Args:
            session_id: UUID of the session
            role: 'user', 'assistant', or 'system'
            content: Message content
            agent_used: Which agent generated this (for assistant messages)
            tool_calls: Tool calls made (for debugging)
        
        Returns:
            Created message record
        """
        # Get next sequence number
        count_response = self.client.table("messages") \
            .select("sequence_number") \
            .eq("session_id", session_id) \
            .order("sequence_number", desc=True) \
            .limit(1) \
            .execute()
        
        next_seq = 1
        if count_response.data:
            next_seq = count_response.data[0]["sequence_number"] + 1
        
        data = {
            "session_id": session_id,
            "role": role,
            "content": content,
            "sequence_number": next_seq,
        }
        
        if agent_used:
            data["agent_used"] = agent_used
        if tool_calls:
            data["tool_calls"] = tool_calls
        
        response = self.client.table("messages").insert(data).execute()
        return response.data[0] if response.data else None
    

    # ==================== Meal Plans (Optional) ====================
    
    def save_meal_plan(
        self,
        session_id: str,
        meals: dict,
        nutrition_totals: dict = None,
        plan_date: str = None,
    ) -> dict:
        """
        Save a generated meal plan.
        
        Args:
            session_id: UUID of the session
            meals: Meal plan structure
            nutrition_totals: Daily totals
            plan_date: Date for the plan (defaults to today)
        
        Returns:
            Created meal plan record
        """
        data = {
            "session_id": session_id,
            "meals": meals,
            "plan_date": plan_date or date.today().isoformat(),
        }
        
        if nutrition_totals:
            data["nutrition_totals"] = nutrition_totals
        
        response = self.client.table("meal_plans").insert(data).execute()
        return response.data[0] if response.data else None
    
    def get_meal_plans(
        self,
        session_id: str,
        limit: int = 7,
    ) -> list[dict]:
        """Get recent meal plans for a session."""
        response = self.client.table("meal_plans") \
            .select("*") \
            .eq("session_id", session_id) \
            .order("plan_date", desc=True) \
            .limit(limit) \
            .execute()
        
        return response.data or []
    
# Singleton instance
supabase_client = SupabaseClient()
