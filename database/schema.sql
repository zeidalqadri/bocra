-- BOCRA Database Schema with IP-based Document Isolation
-- This schema ensures complete data separation between different IP addresses

-- Create schema for all BOCRA tables
CREATE SCHEMA IF NOT EXISTS bocra_secure;

-- Enable required PostgreSQL extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- Set search path
SET search_path = bocra_secure, public;

-- ==========================================
-- IP-based User Tracking Table
-- ==========================================
CREATE TABLE ip_users (
    ip_hash VARCHAR(64) PRIMARY KEY,
    first_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    document_count INTEGER DEFAULT 0,
    total_pages_processed INTEGER DEFAULT 0,
    storage_used_bytes BIGINT DEFAULT 0,
    processing_time_total INTERVAL DEFAULT '0 seconds',
    settings JSONB DEFAULT '{
        "language": "eng",
        "dpi": 400,
        "psm": 1,
        "fast_mode": false,
        "skip_tables": false
    }'::jsonb,
    quota_limit_bytes BIGINT DEFAULT 1073741824, -- 1GB default
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for ip_users
CREATE INDEX idx_ip_users_last_seen ON ip_users(last_seen DESC);
CREATE INDEX idx_ip_users_active ON ip_users(is_active) WHERE is_active = true;
CREATE INDEX idx_ip_users_storage ON ip_users(storage_used_bytes DESC);

-- ==========================================
-- Documents Table with Full IP Isolation
-- ==========================================
CREATE TABLE documents (
    document_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ip_hash VARCHAR(64) NOT NULL REFERENCES ip_users(ip_hash) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    file_hash VARCHAR(64) NOT NULL, -- SHA256 of original file content
    storage_path TEXT NOT NULL,
    original_size BIGINT NOT NULL,
    compressed_size BIGINT,
    pages INTEGER,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'error', 'cancelled')),
    processing_started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    processing_duration INTERVAL,
    ocr_confidence DECIMAL(5,2),
    language VARCHAR(20) DEFAULT 'eng',
    dpi INTEGER DEFAULT 400,
    psm INTEGER DEFAULT 1,
    fast_mode BOOLEAN DEFAULT false,
    skip_tables BOOLEAN DEFAULT false,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Unique constraint to prevent duplicate file uploads per IP
ALTER TABLE documents ADD CONSTRAINT unique_file_per_ip UNIQUE (ip_hash, file_hash);

-- Indexes for documents table
CREATE INDEX idx_documents_ip_created ON documents(ip_hash, created_at DESC);
CREATE INDEX idx_documents_ip_status ON documents(ip_hash, status);
CREATE INDEX idx_documents_status_processing ON documents(status) WHERE status IN ('pending', 'processing');
CREATE INDEX idx_documents_completed ON documents(completed_at DESC) WHERE status = 'completed';
CREATE INDEX idx_documents_metadata ON documents USING GIN (metadata);

-- ==========================================
-- OCR Results Table (Word-level data)
-- ==========================================
CREATE TABLE ocr_results (
    result_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    ip_hash VARCHAR(64) NOT NULL REFERENCES ip_users(ip_hash) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    word_text TEXT NOT NULL,
    confidence DECIMAL(5,2),
    left_pos INTEGER,
    top_pos INTEGER,
    width INTEGER,
    height INTEGER,
    line_number INTEGER,
    word_number INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for OCR results
CREATE INDEX idx_ocr_document ON ocr_results(document_id, page_number);
CREATE INDEX idx_ocr_ip_hash ON ocr_results(ip_hash);
CREATE INDEX idx_ocr_confidence ON ocr_results(confidence) WHERE confidence < 70;
CREATE INDEX idx_ocr_text_search ON ocr_results USING GIN (to_tsvector('english', word_text));

-- ==========================================
-- Processing Queue with IP Isolation
-- ==========================================
CREATE TABLE processing_queue (
    queue_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    ip_hash VARCHAR(64) NOT NULL REFERENCES ip_users(ip_hash) ON DELETE CASCADE,
    priority INTEGER DEFAULT 5, -- Lower number = higher priority
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    last_error TEXT,
    scheduled_for TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    worker_id VARCHAR(50),
    started_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for processing queue
CREATE INDEX idx_queue_scheduled ON processing_queue(scheduled_for) WHERE worker_id IS NULL;
CREATE INDEX idx_queue_priority ON processing_queue(priority, created_at) WHERE worker_id IS NULL;
CREATE INDEX idx_queue_ip ON processing_queue(ip_hash);
CREATE INDEX idx_queue_worker ON processing_queue(worker_id) WHERE worker_id IS NOT NULL;

-- ==========================================
-- User Sessions Table
-- ==========================================
CREATE TABLE user_sessions (
    session_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ip_hash VARCHAR(64) NOT NULL REFERENCES ip_users(ip_hash) ON DELETE CASCADE,
    session_token VARCHAR(255) NOT NULL UNIQUE,
    ip_address INET NOT NULL,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_accessed TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() + INTERVAL '24 hours',
    is_active BOOLEAN DEFAULT true
);

-- Indexes for sessions
CREATE INDEX idx_sessions_token ON user_sessions(session_token) WHERE is_active = true;
CREATE INDEX idx_sessions_ip_hash ON user_sessions(ip_hash, last_accessed DESC);
CREATE INDEX idx_sessions_expires ON user_sessions(expires_at) WHERE is_active = true;

-- ==========================================
-- Audit Log for Security Tracking
-- ==========================================
CREATE TABLE audit_log (
    log_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ip_hash VARCHAR(64),
    ip_address INET,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id UUID,
    details JSONB DEFAULT '{}'::jsonb,
    success BOOLEAN DEFAULT true,
    error_message TEXT,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for audit log
CREATE INDEX idx_audit_ip_hash ON audit_log(ip_hash, created_at DESC);
CREATE INDEX idx_audit_action ON audit_log(action, created_at DESC);
CREATE INDEX idx_audit_resource ON audit_log(resource_type, resource_id);
CREATE INDEX idx_audit_failed ON audit_log(success, created_at DESC) WHERE success = false;

-- ==========================================
-- Storage Usage Tracking
-- ==========================================
CREATE TABLE storage_usage (
    usage_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ip_hash VARCHAR(64) NOT NULL REFERENCES ip_users(ip_hash) ON DELETE CASCADE,
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    documents_added INTEGER DEFAULT 0,
    documents_deleted INTEGER DEFAULT 0,
    bytes_added BIGINT DEFAULT 0,
    bytes_deleted BIGINT DEFAULT 0,
    total_bytes BIGINT DEFAULT 0,
    total_documents INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(ip_hash, date)
);

-- Index for storage usage
CREATE INDEX idx_storage_usage ON storage_usage(ip_hash, date DESC);

-- ==========================================
-- Row Level Security (RLS) Policies
-- ==========================================

-- Enable RLS on all user-specific tables
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE ocr_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE processing_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE storage_usage ENABLE ROW LEVEL SECURITY;

-- Create RLS policies for documents
CREATE POLICY document_isolation ON documents
    FOR ALL
    USING (ip_hash = current_setting('app.current_ip_hash', true));

-- Create RLS policies for OCR results
CREATE POLICY ocr_results_isolation ON ocr_results
    FOR ALL
    USING (ip_hash = current_setting('app.current_ip_hash', true));

-- Create RLS policies for processing queue
CREATE POLICY queue_isolation ON processing_queue
    FOR ALL
    USING (ip_hash = current_setting('app.current_ip_hash', true));

-- Create RLS policies for sessions
CREATE POLICY session_isolation ON user_sessions
    FOR ALL
    USING (ip_hash = current_setting('app.current_ip_hash', true));

-- Create RLS policies for storage usage
CREATE POLICY storage_isolation ON storage_usage
    FOR ALL
    USING (ip_hash = current_setting('app.current_ip_hash', true));

-- ==========================================
-- Utility Functions
-- ==========================================

-- Function to hash IP addresses consistently
CREATE OR REPLACE FUNCTION hash_ip_address(ip_address TEXT)
RETURNS VARCHAR(64) AS $$
BEGIN
    RETURN encode(digest(ip_address || COALESCE(current_setting('app.salt', true), 'bocra_salt'), 'sha256'), 'hex');
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Function to update user statistics
CREATE OR REPLACE FUNCTION update_user_stats()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        -- Update user stats on new document
        INSERT INTO ip_users (ip_hash, document_count, storage_used_bytes)
        VALUES (NEW.ip_hash, 1, NEW.original_size)
        ON CONFLICT (ip_hash) DO UPDATE SET
            document_count = ip_users.document_count + 1,
            storage_used_bytes = ip_users.storage_used_bytes + NEW.original_size,
            last_seen = NOW(),
            updated_at = NOW();
        
        RETURN NEW;
    
    ELSIF TG_OP = 'DELETE' THEN
        -- Update user stats on document deletion
        UPDATE ip_users 
        SET document_count = document_count - 1,
            storage_used_bytes = storage_used_bytes - OLD.original_size,
            updated_at = NOW()
        WHERE ip_hash = OLD.ip_hash;
        
        RETURN OLD;
    END IF;
    
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Trigger to automatically update user statistics
CREATE TRIGGER update_user_stats_trigger
    AFTER INSERT OR DELETE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_user_stats();

-- Function to clean up expired sessions
CREATE OR REPLACE FUNCTION cleanup_expired_sessions()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    UPDATE user_sessions 
    SET is_active = false
    WHERE expires_at < NOW() AND is_active = true;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Function to archive old audit logs
CREATE OR REPLACE FUNCTION archive_old_audit_logs(retention_days INTEGER DEFAULT 90)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM audit_log 
    WHERE created_at < NOW() - (retention_days || ' days')::INTERVAL;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- ==========================================
-- Useful Views
-- ==========================================

-- View for user statistics
CREATE VIEW user_statistics AS
SELECT 
    u.ip_hash,
    u.first_seen,
    u.last_seen,
    u.document_count,
    u.total_pages_processed,
    u.storage_used_bytes,
    ROUND(u.storage_used_bytes::DECIMAL / 1048576, 2) as storage_used_mb,
    u.quota_limit_bytes,
    ROUND((u.storage_used_bytes::DECIMAL / u.quota_limit_bytes * 100), 2) as quota_used_percent,
    COUNT(CASE WHEN d.status = 'completed' THEN 1 END) as completed_documents,
    COUNT(CASE WHEN d.status = 'processing' THEN 1 END) as processing_documents,
    COUNT(CASE WHEN d.status = 'error' THEN 1 END) as failed_documents,
    AVG(CASE WHEN d.ocr_confidence IS NOT NULL THEN d.ocr_confidence END) as avg_confidence
FROM ip_users u
LEFT JOIN documents d ON u.ip_hash = d.ip_hash
GROUP BY u.ip_hash, u.first_seen, u.last_seen, u.document_count, 
         u.total_pages_processed, u.storage_used_bytes, u.quota_limit_bytes;

-- View for processing metrics
CREATE VIEW processing_metrics AS
SELECT 
    DATE(d.created_at) as processing_date,
    COUNT(DISTINCT d.ip_hash) as unique_users,
    COUNT(*) as documents_processed,
    SUM(d.pages) as total_pages,
    AVG(d.ocr_confidence) as avg_confidence,
    AVG(EXTRACT(EPOCH FROM d.processing_duration)) as avg_processing_time_seconds,
    COUNT(CASE WHEN d.status = 'completed' THEN 1 END) as successful_documents,
    COUNT(CASE WHEN d.status = 'error' THEN 1 END) as failed_documents
FROM documents d
WHERE d.status IN ('completed', 'error')
GROUP BY DATE(d.created_at)
ORDER BY processing_date DESC;

-- View for storage analytics
CREATE VIEW storage_analytics AS
SELECT 
    DATE_TRUNC('month', d.created_at) as month,
    COUNT(DISTINCT d.ip_hash) as active_users,
    COUNT(*) as documents_created,
    SUM(d.original_size) as total_bytes_stored,
    AVG(d.original_size) as avg_document_size,
    SUM(d.pages) as total_pages_processed
FROM documents d
GROUP BY DATE_TRUNC('month', d.created_at)
ORDER BY month DESC;

-- ==========================================
-- Initial Data and Configuration
-- ==========================================

-- Create a default configuration entry
INSERT INTO bocra_secure.ip_users (ip_hash, settings) 
VALUES ('system_default', '{
    "language": "eng",
    "dpi": 400,
    "psm": 1,
    "fast_mode": false,
    "skip_tables": false,
    "max_file_size": 52428800,
    "supported_formats": ["pdf"],
    "retention_days": 30
}'::jsonb)
ON CONFLICT (ip_hash) DO NOTHING;

-- Log schema creation
INSERT INTO bocra_secure.audit_log (
    ip_hash, 
    action, 
    resource_type,
    details,
    created_at
) VALUES (
    'system_default',
    'SCHEMA_CREATED',
    'DATABASE',
    '{"version": "1.0", "tables_created": ["ip_users", "documents", "ocr_results", "processing_queue", "user_sessions", "audit_log", "storage_usage"]}'::jsonb,
    NOW()
);

-- Create indexes for performance
ANALYZE;

COMMENT ON SCHEMA bocra_secure IS 'BOCRA secure schema with IP-based document isolation';
COMMENT ON TABLE ip_users IS 'Tracks users based on IP hash with quotas and settings';
COMMENT ON TABLE documents IS 'Document storage with complete IP-based isolation';
COMMENT ON TABLE ocr_results IS 'Word-level OCR results linked to documents';
COMMENT ON TABLE processing_queue IS 'Job queue for OCR processing with IP isolation';
COMMENT ON TABLE user_sessions IS 'User session management with IP tracking';
COMMENT ON TABLE audit_log IS 'Security audit trail for all system actions';
COMMENT ON TABLE storage_usage IS 'Daily storage usage tracking per IP';