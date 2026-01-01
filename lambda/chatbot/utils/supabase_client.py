"""
Supabase client for Kidney Nutrition Chatbot
Session-first approach (no users for MVP)
"""
import os
from typing import Optional
from datetime import datetime, date, timedelta
from supabase import create_client, Client


class SupabaseClient:
    """Supabase client wrapper."""

    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")

        self.client: Client = create_client(url, key)

    
    # ===== SESSIONS =====
    def create_session(self, title: str = None, metadata: dict = None) -> dict:
        """
        Create a new chat session.
        
        Args:
            title: Optional title for the session
            metadata: Optional metadata (source, device, etc.)
        
        Returns:
            Created session record
        """
        data = {
            "title": title or f"Session {datetime.utcnow().isoformat()}",
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
            limit: Maximum messages to return (most recent)
            for_openai: If True, format for OpenAI messages array

        Returns:
            List of messages (oldest first, but limited to most recent N)
        """
        # Get most recent messages first (desc), then reverse to chronological order
        response = self.client.table("messages") \
            .select("*") \
            .eq("session_id", session_id) \
            .order("sequence_number", desc=True) \
            .limit(limit) \
            .execute()

        # Reverse to get chronological order (oldest first)
        messages = list(reversed(response.data or []))
        print(f"Fetched {len(messages)} messages from Supabase (most recent {limit}).")

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
    
    def update_message(
        self,
        message_id: str,
        content: str = None,
        agent_used: str = None,
        tool_calls: dict = None
    ) -> Optional[dict]:
        """
        Update an existing message.
        
        Args:
            message_id: UUID of the message to update
            content: New content (optional)
            agent_used: Updated agent info (optional)
            tool_calls: Updated tool calls (optional)
        
        Returns:
            Updated message record or None
        """
        data = {}
        
        if content is not None:
            data["content"] = content
        if agent_used is not None:
            data["agent_used"] = agent_used
        if tool_calls is not None:
            data["tool_calls"] = tool_calls
        
        if not data:
            return None
        
        try:
            response = self.client.table("messages") \
                .update(data) \
                .eq("id", message_id) \
                .execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error updating message: {e}")
            return None
        
    def delete_message(self, message_id: str) -> bool:
        """
        Delete a message by ID.
        
        Args:
            message_id: UUID of the message to delete
        
        Returns:
            True if deleted successfully
        """
        try:
            self.client.table("messages") \
                .delete() \
                .eq("id", message_id) \
                .execute()
            return True
        except Exception as e:
            print(f"Error deleting message: {e}")
            return False

    def get_message(self, message_id: str) -> Optional[dict]:
        """Get a single message by ID."""
        try:
            response = self.client.table("messages") \
                .select("*") \
                .eq("id", message_id) \
                .single() \
                .execute()
            return response.data
        except Exception:
            return None

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

    # ==================== Agent Analytics ====================

    def save_agent_analytics(
        self,
        session_id: str,
        agent_name: str,
        response_time_ms: float = None,
        token_count: int = None,
        input_tokens: int = None,
        output_tokens: int = None,
        success: bool = True,
        error_message: str = None,
        handoffs: list[str] = None,
        metadata: dict = None,
    ) -> dict:
        """
        Save agent analytics data.

        Args:
            session_id: UUID of the session
            agent_name: Name of the agent that handled the request
            response_time_ms: Response time in milliseconds
            token_count: Total tokens used (deprecated, use input/output)
            input_tokens: Input/prompt tokens
            output_tokens: Completion tokens
            success: Whether the request was successful
            error_message: Error message if failed
            handoffs: List of agents that were handed off to
            metadata: Additional metadata (model used, etc.)

        Returns:
            Created analytics record
        """
        data = {
            "session_id": session_id,
            "agent_name": agent_name,
            "success": success,
        }

        if response_time_ms is not None:
            data["response_time_ms"] = response_time_ms
        if token_count is not None:
            data["token_count"] = token_count
        if input_tokens is not None:
            data["input_tokens"] = input_tokens
        if output_tokens is not None:
            data["output_tokens"] = output_tokens
        if error_message:
            data["error_message"] = error_message
        if handoffs:
            data["handoffs"] = handoffs
        if metadata:
            data["metadata"] = metadata

        try:
            response = self.client.table("agent_analytics").insert(data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error saving analytics: {e}")
            return None

    def get_agent_analytics(
        self,
        session_id: str = None,
        agent_name: str = None,
        start_date: str = None,
        end_date: str = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Get agent analytics data with optional filters.

        Args:
            session_id: Filter by session (optional)
            agent_name: Filter by agent name (optional)
            start_date: Filter by start date (ISO format, optional)
            end_date: Filter by end date (ISO format, optional)
            limit: Maximum records to return

        Returns:
            List of analytics records
        """
        query = self.client.table("agent_analytics").select("*")

        if session_id:
            query = query.eq("session_id", session_id)
        if agent_name:
            query = query.eq("agent_name", agent_name)
        if start_date:
            query = query.gte("created_at", start_date)
        if end_date:
            query = query.lte("created_at", end_date)

        response = query.order("created_at", desc=True).limit(limit).execute()
        return response.data or []

    def get_agent_summary(self, days: int = 7) -> dict:
        """
        Get agent usage summary for the last N days.

        Args:
            days: Number of days to analyze (default: 7)

        Returns:
            Dictionary with agent usage statistics
        """
        try:
            # Calculate start date
            start_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

            # Get all analytics since start_date
            analytics = self.get_agent_analytics(start_date=start_date, limit=10000)

            # Calculate summary
            summary = {
                "total_requests": len(analytics),
                "successful_requests": sum(1 for a in analytics if a.get("success", True)),
                "failed_requests": sum(1 for a in analytics if not a.get("success", True)),
                "by_agent": {},
                "avg_response_time_ms": 0,
                "total_tokens": 0,
            }

            # Calculate per-agent stats
            agent_stats = {}
            total_response_time = 0
            response_time_count = 0

            for record in analytics:
                agent = record.get("agent_name", "Unknown")

                if agent not in agent_stats:
                    agent_stats[agent] = {
                        "count": 0,
                        "success_count": 0,
                        "total_response_time": 0,
                        "total_tokens": 0,
                    }

                agent_stats[agent]["count"] += 1

                if record.get("success", True):
                    agent_stats[agent]["success_count"] += 1

                if record.get("response_time_ms"):
                    agent_stats[agent]["total_response_time"] += record["response_time_ms"]
                    total_response_time += record["response_time_ms"]
                    response_time_count += 1

                tokens = record.get("token_count") or (
                    (record.get("input_tokens") or 0) + (record.get("output_tokens") or 0)
                )
                agent_stats[agent]["total_tokens"] += tokens
                summary["total_tokens"] += tokens

            # Calculate averages
            for agent, stats in agent_stats.items():
                summary["by_agent"][agent] = {
                    "count": stats["count"],
                    "success_rate": stats["success_count"] / stats["count"] if stats["count"] > 0 else 0,
                    "avg_response_time_ms": stats["total_response_time"] / stats["count"] if stats["count"] > 0 else 0,
                    "total_tokens": stats["total_tokens"],
                }

            if response_time_count > 0:
                summary["avg_response_time_ms"] = total_response_time / response_time_count

            return summary

        except Exception as e:
            print(f"Error generating agent summary: {e}")
            return {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "by_agent": {},
                "avg_response_time_ms": 0,
                "total_tokens": 0,
            }

    # ==================== Session Feedback ====================

    def save_session_feedback(
        self,
        session_id: str,
        rating: int,
        comment: str = None,
        user_agent: str = None,
        ip_address: str = None,
        device_info: dict = None,
    ) -> dict:
        """
        Save user feedback for a chat session.

        Args:
            session_id: UUID of the session
            rating: User rating from 1-5 (1=very sad, 5=very happy)
            comment: Optional user comment
            user_agent: Browser user agent string
            ip_address: User IP address
            device_info: Additional device/browser information

        Returns:
            Created feedback record or None
        """
        if not 1 <= rating <= 5:
            raise ValueError("Rating must be between 1 and 5")

        data = {
            "session_id": session_id,
            "rating": rating,
        }

        if comment:
            data["comment"] = comment
        if user_agent:
            data["user_agent"] = user_agent
        if ip_address:
            data["ip_address"] = ip_address
        if device_info:
            data["device_info"] = device_info

        try:
            response = self.client.table("session_feedback").insert(data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error saving session feedback: {e}")
            return None

    def get_session_feedback(self, session_id: str) -> dict:
        """
        Get feedback for a specific session.

        Args:
            session_id: UUID of the session

        Returns:
            Feedback record or None
        """
        try:
            response = self.client.table("session_feedback") \
                .select("*") \
                .eq("session_id", session_id) \
                .single() \
                .execute()
            return response.data
        except Exception:
            return None

    def get_feedback_summary(self, days: int = 30) -> dict:
        """
        Get feedback summary statistics.

        Args:
            days: Number of days to analyze (default: 30)

        Returns:
            Dictionary with feedback statistics
        """
        try:
            from datetime import datetime, timedelta

            # Calculate start date
            start_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

            # Get all feedback since start_date
            response = self.client.table("session_feedback") \
                .select("*") \
                .gte("created_at", start_date) \
                .execute()

            feedback_list = response.data or []

            # Calculate summary
            if not feedback_list:
                return {
                    "total_responses": 0,
                    "average_rating": 0,
                    "rating_distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
                    "with_comments": 0,
                }

            total = len(feedback_list)
            avg_rating = sum(f["rating"] for f in feedback_list) / total
            with_comments = sum(1 for f in feedback_list if f.get("comment"))

            # Count rating distribution
            rating_dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            for feedback in feedback_list:
                rating_dist[feedback["rating"]] += 1

            return {
                "total_responses": total,
                "average_rating": round(avg_rating, 2),
                "rating_distribution": rating_dist,
                "with_comments": with_comments,
                "satisfaction_rate": round((rating_dist[4] + rating_dist[5]) / total * 100, 1),
            }

        except Exception as e:
            print(f"Error generating feedback summary: {e}")
            return {
                "total_responses": 0,
                "average_rating": 0,
                "rating_distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
                "with_comments": 0,
                "satisfaction_rate": 0,
            }

# Singleton instance
supabase_client = SupabaseClient()
