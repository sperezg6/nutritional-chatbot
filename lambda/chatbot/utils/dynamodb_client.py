"""
DynamoDB client for Kidney Nutrition Chatbot
Session-first approach (no users for MVP)
Drop-in replacement for SupabaseClient with identical method signatures.
"""
import os
import uuid
from typing import Optional
import time as _time
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

# Module-level resource (reused across invocations)
_dynamodb = boto3.resource("dynamodb")

SESSIONS_TABLE = os.getenv("SESSIONS_TABLE", "nutritional-chatbot-sessions")
MESSAGES_TABLE = os.getenv("MESSAGES_TABLE", "nutritional-chatbot-messages")
ANALYTICS_TABLE = os.getenv("ANALYTICS_TABLE", "nutritional-chatbot-analytics")
FEEDBACK_TABLE = os.getenv("FEEDBACK_TABLE", "nutritional-chatbot-feedback")


def _clean_item(item: dict) -> dict:
    """Convert Decimal values back to int/float for JSON compatibility."""
    if item is None:
        return None
    cleaned = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            cleaned[k] = int(v) if v == int(v) else float(v)
        elif isinstance(v, dict):
            cleaned[k] = _clean_item(v)
        elif isinstance(v, list):
            cleaned[k] = [
                _clean_item(i) if isinstance(i, dict)
                else (int(i) if isinstance(i, Decimal) and i == int(i) else float(i) if isinstance(i, Decimal) else i)
                for i in v
            ]
        else:
            cleaned[k] = v
    return cleaned


class DynamoDBClient:
    """DynamoDB client wrapper — same interface as SupabaseClient."""

    def __init__(self):
        self.sessions = _dynamodb.Table(SESSIONS_TABLE)
        self.messages = _dynamodb.Table(MESSAGES_TABLE)
        self.analytics = _dynamodb.Table(ANALYTICS_TABLE)
        self.feedback = _dynamodb.Table(FEEDBACK_TABLE)

    # ===== SESSIONS =====

    def create_session(self, title: str = None, metadata: dict = None) -> dict:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        item = {
            "session_id": session_id,
            "id": session_id,  # alias kept for compatibility
            "title": title or f"Session {now}",
            "metadata": metadata or {},
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        self.sessions.put_item(Item=item)
        return _clean_item(item)

    def get_session(self, session_id: str) -> Optional[dict]:
        try:
            resp = self.sessions.get_item(Key={"session_id": session_id})
            item = resp.get("Item")
            if item:
                item["id"] = item["session_id"]  # compatibility alias
            return _clean_item(item)
        except Exception:
            return None

    def end_session(self, session_id: str) -> dict:
        resp = self.sessions.update_item(
            Key={"session_id": session_id},
            UpdateExpression="SET is_active = :val, updated_at = :now",
            ExpressionAttributeValues={
                ":val": False,
                ":now": datetime.now(timezone.utc).isoformat(),
            },
            ReturnValues="ALL_NEW",
        )
        item = resp.get("Attributes")
        if item:
            item["id"] = item["session_id"]
        return _clean_item(item)

    # ===== MESSAGES =====

    def get_messages(
        self,
        session_id: str,
        limit: int = 20,
        for_openai: bool = True,
    ) -> list[dict]:
        resp = self.messages.query(
            KeyConditionExpression=Key("session_id").eq(session_id),
            ScanIndexForward=False,  # newest first
            Limit=limit,
        )
        messages = list(reversed(resp.get("Items", [])))  # chronological
        print(f"Fetched {len(messages)} messages from DynamoDB (most recent {limit}).")

        if for_openai:
            return [
                {"role": msg["role"], "content": msg["content"]}
                for msg in messages
            ]
        return [_clean_item(m) for m in messages]

    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        agent_used: str = None,
        tool_calls: dict = None,
    ) -> dict:
        # Use microsecond-precision timestamp as sort key (no read-before-write)
        next_seq = int(_time.time() * 1_000_000)

        message_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        item = {
            "session_id": session_id,
            "sequence_number": next_seq,
            "message_id": message_id,
            "id": message_id,  # compatibility alias
            "role": role,
            "content": content,
            "created_at": now,
        }
        if agent_used:
            item["agent_used"] = agent_used
        if tool_calls:
            item["tool_calls"] = tool_calls

        self.messages.put_item(Item=item)
        return _clean_item(item)

    def _get_message_keys_by_id(self, message_id: str) -> Optional[dict]:
        """Query GSI to get the composite key for a message."""
        resp = self.messages.query(
            IndexName="by_message_id",
            KeyConditionExpression=Key("message_id").eq(message_id),
            Limit=1,
        )
        items = resp.get("Items", [])
        if not items:
            return None
        return {
            "session_id": items[0]["session_id"],
            "sequence_number": items[0]["sequence_number"],
        }

    def update_message(
        self,
        message_id: str,
        content: str = None,
        agent_used: str = None,
        tool_calls: dict = None,
    ) -> Optional[dict]:
        keys = self._get_message_keys_by_id(message_id)
        if not keys:
            return None

        expressions = []
        values = {}
        names = {}

        if content is not None:
            expressions.append("#c = :content")
            values[":content"] = content
            names["#c"] = "content"
        if agent_used is not None:
            expressions.append("agent_used = :agent")
            values[":agent"] = agent_used
        if tool_calls is not None:
            expressions.append("tool_calls = :tc")
            values[":tc"] = tool_calls

        if not expressions:
            return None

        try:
            resp = self.messages.update_item(
                Key=keys,
                UpdateExpression="SET " + ", ".join(expressions),
                ExpressionAttributeValues=values,
                **({"ExpressionAttributeNames": names} if names else {}),
                ReturnValues="ALL_NEW",
            )
            return _clean_item(resp.get("Attributes"))
        except Exception as e:
            print(f"Error updating message: {e}")
            return None

    def delete_message(self, message_id: str) -> bool:
        keys = self._get_message_keys_by_id(message_id)
        if not keys:
            return False
        try:
            self.messages.delete_item(Key=keys)
            return True
        except Exception as e:
            print(f"Error deleting message: {e}")
            return False

    def get_message(self, message_id: str) -> Optional[dict]:
        resp = self.messages.query(
            IndexName="by_message_id",
            KeyConditionExpression=Key("message_id").eq(message_id),
            Limit=1,
        )
        items = resp.get("Items", [])
        return _clean_item(items[0]) if items else None

    # ===== AGENT ANALYTICS =====

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
        now = datetime.now(timezone.utc).isoformat()
        date_partition = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        item = {
            "session_id": session_id,
            "created_at": now,
            "date_partition": date_partition,
            "agent_name": agent_name,
            "success": success,
        }

        if response_time_ms is not None:
            item["response_time_ms"] = Decimal(str(round(response_time_ms, 2)))
        if token_count is not None:
            item["token_count"] = token_count
        if input_tokens is not None:
            item["input_tokens"] = input_tokens
        if output_tokens is not None:
            item["output_tokens"] = output_tokens
        if error_message:
            item["error_message"] = error_message
        if handoffs:
            item["handoffs"] = handoffs
        if metadata:
            item["metadata"] = metadata

        try:
            self.analytics.put_item(Item=item)
            return _clean_item(item)
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
        try:
            if session_id:
                # Query by session_id (PK)
                kce = Key("session_id").eq(session_id)
                resp = self.analytics.query(
                    KeyConditionExpression=kce,
                    ScanIndexForward=False,
                    Limit=limit,
                )
                items = resp.get("Items", [])
            elif start_date:
                # Use GSI by_date for date range queries
                kce = Key("date_partition").eq(start_date[:10])
                if end_date:
                    kce = kce & Key("created_at").between(start_date, end_date)

                # Query each day in range
                items = []
                current = datetime.fromisoformat(start_date[:10])
                end = datetime.fromisoformat(end_date[:10]) if end_date else datetime.now(timezone.utc)

                while current <= end and len(items) < limit:
                    day_str = current.strftime("%Y-%m-%d")
                    resp = self.analytics.query(
                        IndexName="by_date",
                        KeyConditionExpression=Key("date_partition").eq(day_str),
                        ScanIndexForward=False,
                        Limit=limit - len(items),
                    )
                    items.extend(resp.get("Items", []))
                    current += timedelta(days=1)
            else:
                # Fallback: scan (not ideal but matches original behavior)
                resp = self.analytics.scan(Limit=limit)
                items = resp.get("Items", [])

            # Apply agent_name filter in Python (same as Supabase .eq())
            if agent_name:
                items = [i for i in items if i.get("agent_name") == agent_name]

            return [_clean_item(i) for i in items]
        except Exception as e:
            print(f"Error getting analytics: {e}")
            return []

    def get_agent_summary(self, days: int = 7) -> dict:
        try:
            start = datetime.now(timezone.utc) - timedelta(days=days)
            items = []

            current = start
            while current <= datetime.now(timezone.utc):
                day_str = current.strftime("%Y-%m-%d")
                resp = self.analytics.query(
                    IndexName="by_date",
                    KeyConditionExpression=Key("date_partition").eq(day_str),
                    ScanIndexForward=False,
                )
                items.extend(resp.get("Items", []))
                current += timedelta(days=1)

            analytics = [_clean_item(i) for i in items]

            summary = {
                "total_requests": len(analytics),
                "successful_requests": sum(1 for a in analytics if a.get("success", True)),
                "failed_requests": sum(1 for a in analytics if not a.get("success", True)),
                "by_agent": {},
                "avg_response_time_ms": 0,
                "total_tokens": 0,
            }

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

    # ===== SESSION FEEDBACK =====

    def save_session_feedback(
        self,
        session_id: str,
        rating: int,
        comment: str = None,
        user_agent: str = None,
        ip_address: str = None,
        device_info: dict = None,
    ) -> dict:
        if not 1 <= rating <= 5:
            raise ValueError("Rating must be between 1 and 5")

        now = datetime.now(timezone.utc).isoformat()
        date_partition = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        item = {
            "session_id": session_id,
            "created_at": now,
            "date_partition": date_partition,
            "rating": rating,
        }
        if comment:
            item["comment"] = comment
        if user_agent:
            item["user_agent"] = user_agent
        if ip_address:
            item["ip_address"] = ip_address
        if device_info:
            item["device_info"] = device_info

        try:
            self.feedback.put_item(Item=item)
            return _clean_item(item)
        except Exception as e:
            print(f"Error saving session feedback: {e}")
            return None

    def get_session_feedback(self, session_id: str) -> dict:
        try:
            resp = self.feedback.query(
                KeyConditionExpression=Key("session_id").eq(session_id),
                ScanIndexForward=False,
                Limit=1,
            )
            items = resp.get("Items", [])
            return _clean_item(items[0]) if items else None
        except Exception:
            return None

    def get_feedback_summary(self, days: int = 30) -> dict:
        try:
            start = datetime.now(timezone.utc) - timedelta(days=days)
            items = []

            current = start
            while current <= datetime.now(timezone.utc):
                day_str = current.strftime("%Y-%m-%d")
                resp = self.feedback.query(
                    IndexName="by_date",
                    KeyConditionExpression=Key("date_partition").eq(day_str),
                    ScanIndexForward=False,
                )
                items.extend(resp.get("Items", []))
                current += timedelta(days=1)

            feedback_list = [_clean_item(i) for i in items]

            if not feedback_list:
                return {
                    "total_responses": 0,
                    "average_rating": 0,
                    "rating_distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
                    "with_comments": 0,
                    "satisfaction_rate": 0,
                }

            total = len(feedback_list)
            avg_rating = sum(f["rating"] for f in feedback_list) / total
            with_comments = sum(1 for f in feedback_list if f.get("comment"))

            rating_dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            for fb in feedback_list:
                rating_dist[fb["rating"]] += 1

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
dynamodb_client = DynamoDBClient()
