# Agent Analytics System

## Overview

The agent analytics system tracks performance metrics for all agent interactions including:
- Response times
- Token usage (input/output)
- Success/failure rates
- Agent usage patterns
- Error tracking

## Database Setup

### 1. Run the Migration

Execute the SQL migration in your Supabase dashboard or using the Supabase CLI:

```bash
# Using Supabase CLI
supabase db push

# Or manually in Supabase SQL Editor
# Copy and paste the contents of migrations/003_agent_analytics.sql
```

### 2. Verify the Table

After running the migration, verify the table was created:

```sql
SELECT * FROM agent_analytics LIMIT 1;
```

## Using the Analytics API

### Save Analytics Data

The system automatically saves analytics for each request. This is handled in `handler.py`:

```python
# Success case
supabase.save_agent_analytics(
    session_id=session_id,
    agent_name=agent_used,
    response_time_ms=response_time_ms,
    success=True,
)

# Error case
supabase.save_agent_analytics(
    session_id=session_id,
    agent_name="OrchestratorAgent",
    response_time_ms=response_time_ms,
    success=False,
    error_message=str(error),
)
```

### Query Analytics

#### Get Analytics for a Session

```python
from utils.supabase_client import SupabaseClient

supabase = SupabaseClient()

# Get all analytics for a specific session
analytics = supabase.get_agent_analytics(session_id="your-session-id")

for record in analytics:
    print(f"Agent: {record['agent_name']}")
    print(f"Response Time: {record['response_time_ms']}ms")
    print(f"Success: {record['success']}")
```

#### Get Analytics by Agent

```python
# Get all analytics for a specific agent
analytics = supabase.get_agent_analytics(agent_name="NutritionPlanAgent")
```

#### Get Analytics for Date Range

```python
# Get analytics for last 7 days
from datetime import datetime, timedelta

start_date = (datetime.utcnow() - timedelta(days=7)).isoformat()
analytics = supabase.get_agent_analytics(start_date=start_date)
```

#### Get Agent Summary

```python
# Get summary statistics for last 7 days
summary = supabase.get_agent_summary(days=7)

print(f"Total Requests: {summary['total_requests']}")
print(f"Success Rate: {summary['successful_requests'] / summary['total_requests']}")
print(f"Avg Response Time: {summary['avg_response_time_ms']}ms")
print(f"Total Tokens: {summary['total_tokens']}")

# Per-agent breakdown
for agent_name, stats in summary['by_agent'].items():
    print(f"\n{agent_name}:")
    print(f"  Count: {stats['count']}")
    print(f"  Success Rate: {stats['success_rate']*100:.2f}%")
    print(f"  Avg Response Time: {stats['avg_response_time_ms']:.2f}ms")
    print(f"  Total Tokens: {stats['total_tokens']}")
```

## Analytics Schema

```sql
CREATE TABLE agent_analytics (
    id UUID PRIMARY KEY,
    session_id UUID REFERENCES sessions(id),
    agent_name VARCHAR(100),

    -- Performance
    response_time_ms NUMERIC(10, 2),
    token_count INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,

    -- Status
    success BOOLEAN,
    error_message TEXT,

    -- Additional
    handoffs TEXT[],
    metadata JSONB,

    created_at TIMESTAMPTZ
);
```

## Example Queries

### Most Used Agents (Last 30 Days)

```sql
SELECT
    agent_name,
    COUNT(*) as usage_count,
    AVG(response_time_ms) as avg_response_time,
    SUM(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)) as total_tokens
FROM agent_analytics
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY agent_name
ORDER BY usage_count DESC;
```

### Success Rate by Agent

```sql
SELECT
    agent_name,
    COUNT(*) as total_requests,
    SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful_requests,
    ROUND(100.0 * SUM(CASE WHEN success THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate_pct
FROM agent_analytics
GROUP BY agent_name
ORDER BY success_rate_pct DESC;
```

### Slowest Responses

```sql
SELECT
    session_id,
    agent_name,
    response_time_ms,
    created_at
FROM agent_analytics
WHERE response_time_ms IS NOT NULL
ORDER BY response_time_ms DESC
LIMIT 10;
```

### Error Tracking

```sql
SELECT
    agent_name,
    error_message,
    COUNT(*) as error_count,
    MAX(created_at) as last_occurred
FROM agent_analytics
WHERE success = FALSE
GROUP BY agent_name, error_message
ORDER BY error_count DESC;
```

## Dashboard Integration

You can create a dashboard in Supabase or your preferred BI tool using these queries to monitor:

1. **Agent Performance**: Response times, token usage
2. **Usage Patterns**: Most/least used agents
3. **Error Rates**: Failure patterns and error messages
4. **Cost Tracking**: Token usage trends
5. **User Experience**: Session-level performance metrics

## Notes

- Analytics are saved **after** each request completes
- Failed requests also save analytics (with `success=FALSE`)
- Response time includes the entire processing time from start to finish
- Token counts may be `NULL` if not available from the AI provider
- The `metadata` field can store additional context (model name, temperature, etc.)
