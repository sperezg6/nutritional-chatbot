-- Migration: Create agent_analytics table for tracking agent performance
-- Created: 2025-12-11
-- Description: Tracks agent usage, response times, tokens, and errors

CREATE TABLE IF NOT EXISTS agent_analytics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    agent_name VARCHAR(100) NOT NULL,

    -- Performance metrics
    response_time_ms NUMERIC(10, 2),  -- Response time in milliseconds
    token_count INTEGER,               -- Total tokens (deprecated, use input/output)
    input_tokens INTEGER,              -- Prompt/input tokens
    output_tokens INTEGER,             -- Completion/output tokens

    -- Status tracking
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,

    -- Additional data
    handoffs TEXT[],                   -- Array of agent names handed off to
    metadata JSONB,                    -- Additional metadata (model, etc.)

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Indexes for common queries
    INDEX idx_agent_analytics_session (session_id),
    INDEX idx_agent_analytics_agent (agent_name),
    INDEX idx_agent_analytics_created (created_at DESC),
    INDEX idx_agent_analytics_success (success)
);

-- Add comments for documentation
COMMENT ON TABLE agent_analytics IS 'Tracks agent performance metrics and usage analytics';
COMMENT ON COLUMN agent_analytics.session_id IS 'Reference to the session this analytics record belongs to';
COMMENT ON COLUMN agent_analytics.agent_name IS 'Name of the agent that handled the request';
COMMENT ON COLUMN agent_analytics.response_time_ms IS 'Total response time in milliseconds';
COMMENT ON COLUMN agent_analytics.token_count IS 'Total tokens used (deprecated in favor of input/output)';
COMMENT ON COLUMN agent_analytics.input_tokens IS 'Number of input/prompt tokens';
COMMENT ON COLUMN agent_analytics.output_tokens IS 'Number of output/completion tokens';
COMMENT ON COLUMN agent_analytics.success IS 'Whether the request completed successfully';
COMMENT ON COLUMN agent_analytics.error_message IS 'Error message if the request failed';
COMMENT ON COLUMN agent_analytics.handoffs IS 'Array of agent names that were handed off to';
COMMENT ON COLUMN agent_analytics.metadata IS 'Additional metadata (model name, temperature, etc.)';

-- Enable Row Level Security (RLS)
ALTER TABLE agent_analytics ENABLE ROW LEVEL SECURITY;

-- Create policy to allow service role full access
CREATE POLICY "Service role has full access to agent_analytics"
    ON agent_analytics
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Optional: Create policy for anon users to read their own session analytics
CREATE POLICY "Users can view analytics for their sessions"
    ON agent_analytics
    FOR SELECT
    TO anon
    USING (
        session_id IN (
            SELECT id FROM sessions
            WHERE sessions.id = agent_analytics.session_id
        )
    );
