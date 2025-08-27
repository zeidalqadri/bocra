"""
BOCRA FastAPI Application
Main API server for OCR processing with IP-based isolation
"""

import os
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pathlib import Path
import tempfile

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.security import HTTPBearer
import asyncpg
import redis.asyncio as redis
import uvicorn

from .session_manager import SessionManager
from .secure_storage import SecureFileStorage
from .api_security import authenticate_request, SecurityContext, SecurityPolicy
from .monitoring_jobs import MonitoringService, CleanupService
from ..ocr_fulltext import process_pdf_file

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="BOCRA API",
    description="High-fidelity OCR processing with IP-based isolation",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# CORS Configuration
FRONTEND_URLS = os.getenv("FRONTEND_URLS", "http://localhost:3000,https://*.pages.dev").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_URLS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Global variables for services
session_manager: Optional[SessionManager] = None
secure_storage: Optional[SecureFileStorage] = None
monitoring_service: Optional[MonitoringService] = None
cleanup_service: Optional[CleanupService] = None
security_policy: Optional[SecurityPolicy] = None

# Background task tracking
processing_tasks: Dict[str, Dict[str, Any]] = {}

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global session_manager, secure_storage, monitoring_service, cleanup_service, security_policy
    
    try:
        # Database connection
        DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://bocra:bocra@localhost:5432/bocra")
        REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
        STORAGE_PATH = os.getenv("STORAGE_PATH", "/var/lib/bocra/storage")
        
        # Initialize session manager
        session_manager = SessionManager(
            database_url=DATABASE_URL,
            redis_url=REDIS_URL,
            secret_key=os.getenv("BOCRA_SECRET_KEY"),
            session_duration_hours=int(os.getenv("SESSION_DURATION_HOURS", "24")),
            ip_salt=os.getenv("BOCRA_IP_SALT")
        )
        await session_manager.initialize()
        
        # Initialize secure storage
        secure_storage = SecureFileStorage(
            base_storage_path=STORAGE_PATH,
            encryption_key=os.getenv("BOCRA_STORAGE_KEY")
        )
        
        # Initialize Redis for monitoring
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        
        # Initialize monitoring services
        monitoring_service = MonitoringService(session_manager, secure_storage, redis_client)
        cleanup_service = CleanupService(session_manager, secure_storage)
        
        # Initialize security policy
        security_policy = SecurityPolicy(
            max_documents_per_ip=int(os.getenv("MAX_DOCUMENTS_PER_IP", "1000")),
            max_storage_bytes_per_ip=int(os.getenv("MAX_STORAGE_BYTES_PER_IP", "10737418240")),  # 10GB
            max_file_size_bytes=int(os.getenv("MAX_FILE_SIZE_BYTES", "104857600")),  # 100MB
            allowed_file_types=[".pdf"]
        )
        
        logger.info("BOCRA API started successfully")
    
    except Exception as e:
        logger.error(f"Failed to start BOCRA API: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global session_manager
    
    if session_manager:
        await session_manager.close()
    
    logger.info("BOCRA API shut down successfully")

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0"
    }

@app.post("/api/session/init")
async def initialize_session(security_context: SecurityContext = Depends(authenticate_request)):
    """Initialize a new user session"""
    return {
        "sessionToken": security_context.session.session_token,
        "ipHash": security_context.ip_hash,
        "expiresAt": security_context.session.expires_at.isoformat(),
        "isActive": security_context.session.is_active
    }

@app.get("/api/user/info")
async def get_user_info(security_context: SecurityContext = Depends(authenticate_request)):
    """Get user information and statistics"""
    user_info = await session_manager.get_user_info(security_context.ip_address)
    
    if not user_info:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "ipHash": user_info["ip_hash"],
        "documentCount": user_info["document_count"],
        "storageUsedBytes": user_info["storage_used_bytes"],
        "quotaLimitBytes": user_info["quota_limit_bytes"],
        "quotaUsedPercent": user_info["quota_used_percent"],
        "activeSessionsCount": user_info["active_sessions"],
        "firstSeen": user_info["first_seen"].isoformat(),
        "lastSeen": user_info["last_seen"].isoformat(),
        "settings": user_info["settings"]
    }

@app.put("/api/user/settings")
async def update_user_settings(
    settings: Dict[str, Any],
    security_context: SecurityContext = Depends(authenticate_request)
):
    """Update user settings"""
    success = await session_manager.update_user_settings(security_context.ip_address, settings)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update settings")
    
    return {"success": True}

@app.post("/api/documents/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    settings: str = Form(...),
    security_context: SecurityContext = Depends(authenticate_request)
):
    """Upload document for OCR processing"""
    import json
    
    try:
        # Parse settings
        ocr_settings = json.loads(settings)
        
        # Validate file
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")
        
        # Read file content
        file_content = await file.read()
        
        # Check security policy
        user_info = await session_manager.get_user_info(security_context.ip_address)
        if user_info:
            await security_policy.check_upload_policy(
                security_context,
                file.filename,
                len(file_content),
                user_info["document_count"],
                user_info["storage_used_bytes"]
            )
        
        # Generate document ID
        document_id = str(uuid.uuid4())
        
        # Store file securely
        stored_doc = await secure_storage.store_document(
            security_context.ip_hash,
            document_id,
            file.filename,
            file_content,
            metadata={
                "ocr_settings": ocr_settings,
                "uploaded_by": security_context.ip_hash,
                "upload_time": datetime.now(timezone.utc).isoformat()
            }
        )
        
        # Store document record in database
        async with session_manager._db_pool.acquire() as conn:
            await conn.execute("SET LOCAL app.current_ip_hash = $1", security_context.ip_hash)
            await conn.execute("""
                INSERT INTO documents (
                    document_id, ip_hash, filename, file_hash, storage_path,
                    original_size, pages, status, language, dpi, psm, fast_mode, skip_tables
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            """, 
                document_id, security_context.ip_hash, file.filename, stored_doc.file_hash,
                stored_doc.storage_path, stored_doc.original_size, 0, 'pending',
                ocr_settings.get('language', 'eng'), ocr_settings.get('dpi', 400),
                ocr_settings.get('psm', 1), ocr_settings.get('fastMode', False),
                ocr_settings.get('skipTables', False)
            )
        
        # Initialize processing status
        processing_tasks[document_id] = {
            "documentId": document_id,
            "status": "pending",
            "progress": 0,
            "currentPage": 0,
            "totalPages": 0,
            "confidence": 0,
            "estimatedTimeRemaining": 0
        }
        
        # Queue background OCR processing
        background_tasks.add_task(process_document_ocr, document_id, security_context.ip_hash, ocr_settings)
        
        return {
            "documentId": document_id,
            "message": "Document uploaded successfully, processing started"
        }
    
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/documents/{document_id}/status")
async def get_document_status(
    document_id: str,
    security_context: SecurityContext = Depends(authenticate_request)
):
    """Get document processing status"""
    
    # Check if document belongs to this IP
    async with session_manager._db_pool.acquire() as conn:
        await conn.execute("SET LOCAL app.current_ip_hash = $1", security_context.ip_hash)
        doc = await conn.fetchrow("""
            SELECT status, pages, ocr_confidence 
            FROM documents 
            WHERE document_id = $1
        """, document_id)
        
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Get processing status from memory or database
        if document_id in processing_tasks:
            status_data = processing_tasks[document_id]
        else:
            status_data = {
                "documentId": document_id,
                "status": doc["status"],
                "progress": 100 if doc["status"] == "completed" else 0,
                "currentPage": doc["pages"] if doc["pages"] else 0,
                "totalPages": doc["pages"] if doc["pages"] else 0,
                "confidence": float(doc["ocr_confidence"]) if doc["ocr_confidence"] else 0,
                "estimatedTimeRemaining": 0
            }
        
        return status_data

@app.get("/api/documents")
async def list_documents(
    offset: int = 0,
    limit: int = 20,
    status: Optional[str] = None,
    security_context: SecurityContext = Depends(authenticate_request)
):
    """List user's documents"""
    
    async with session_manager._db_pool.acquire() as conn:
        await conn.execute("SET LOCAL app.current_ip_hash = $1", security_context.ip_hash)
        
        # Build query
        where_clause = ""
        params = [limit, offset]
        param_count = 2
        
        if status:
            param_count += 1
            where_clause = f" AND status = ${param_count}"
            params.append(status)
        
        # Get documents
        query = f"""
            SELECT document_id, filename, original_size, pages, status, 
                   created_at, completed_at, ocr_confidence
            FROM documents 
            WHERE ip_hash = $3 {where_clause}
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
        """
        params.append(security_context.ip_hash)
        
        docs = await conn.fetch(query, *params)
        
        # Get total count
        count_query = f"SELECT COUNT(*) FROM documents WHERE ip_hash = $1 {where_clause}"
        count_params = [security_context.ip_hash]
        if status:
            count_params.append(status)
        
        total = await conn.fetchval(count_query, *count_params)
        
        return {
            "documents": [
                {
                    "id": doc["document_id"],
                    "filename": doc["filename"],
                    "originalSize": doc["original_size"],
                    "pages": doc["pages"],
                    "status": doc["status"],
                    "createdAt": doc["created_at"].isoformat(),
                    "completedAt": doc["completed_at"].isoformat() if doc["completed_at"] else None,
                    "confidence": float(doc["ocr_confidence"]) if doc["ocr_confidence"] else 0
                }
                for doc in docs
            ],
            "total": total,
            "offset": offset,
            "limit": limit
        }

@app.get("/api/documents/{document_id}/download/{format}")
async def download_document(
    document_id: str,
    format: str,
    security_context: SecurityContext = Depends(authenticate_request)
):
    """Download processed document in specified format"""
    
    if format not in ['txt', 'json', 'csv', 'pdf']:
        raise HTTPException(status_code=400, detail="Unsupported format")
    
    # Verify document ownership and completion
    async with session_manager._db_pool.acquire() as conn:
        await conn.execute("SET LOCAL app.current_ip_hash = $1", security_context.ip_hash)
        doc = await conn.fetchrow("""
            SELECT filename, status FROM documents 
            WHERE document_id = $1
        """, document_id)
        
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        if doc["status"] != "completed":
            raise HTTPException(status_code=400, detail="Document processing not completed")
    
    # For now, return mock data - in production, retrieve processed OCR results
    mock_content = f"Mock {format.upper()} content for document {document_id}"
    
    # Set appropriate content type and filename
    content_types = {
        'txt': 'text/plain',
        'json': 'application/json',
        'csv': 'text/csv',
        'pdf': 'application/pdf'
    }
    
    filename = f"{doc['filename'].rsplit('.', 1)[0]}_ocr.{format}"
    
    return StreamingResponse(
        iter([mock_content.encode()]),
        media_type=content_types[format],
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.delete("/api/documents/{document_id}")
async def delete_document(
    document_id: str,
    security_context: SecurityContext = Depends(authenticate_request)
):
    """Delete a document"""
    
    # Verify document ownership
    async with session_manager._db_pool.acquire() as conn:
        await conn.execute("SET LOCAL app.current_ip_hash = $1", security_context.ip_hash)
        exists = await conn.fetchval("""
            SELECT EXISTS(SELECT 1 FROM documents WHERE document_id = $1)
        """, document_id)
        
        if not exists:
            raise HTTPException(status_code=404, detail="Document not found")
    
    # Delete from secure storage
    success = await secure_storage.delete_document(security_context.ip_hash, document_id)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete document")
    
    return {"success": True}

@app.get("/api/processing/queue-status")
async def get_queue_status():
    """Get processing queue status"""
    
    async with session_manager._db_pool.acquire() as conn:
        queue_length = await conn.fetchval("""
            SELECT COUNT(*) FROM processing_queue WHERE worker_id IS NULL
        """)
        
        active_workers = await conn.fetchval("""
            SELECT COUNT(DISTINCT worker_id) FROM processing_queue 
            WHERE worker_id IS NOT NULL
        """)
    
    return {
        "queueLength": queue_length,
        "estimatedWaitTime": queue_length * 30,  # Estimate 30 seconds per document
        "activeWorkers": active_workers
    }

async def process_document_ocr(document_id: str, ip_hash: str, settings: Dict[str, Any]):
    """Background task to process OCR for a document"""
    try:
        # Update status to processing
        processing_tasks[document_id]["status"] = "processing"
        
        # Get document from storage
        result = await secure_storage.retrieve_document(ip_hash, document_id)
        if not result:
            raise Exception("Document not found in storage")
        
        stored_doc, file_content = result
        
        # Save to temporary file for OCR processing
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            temp_file.write(file_content)
            temp_pdf_path = temp_file.name
        
        try:
            # Mock OCR processing with progress updates
            total_pages = 5  # Mock page count
            processing_tasks[document_id]["totalPages"] = total_pages
            
            for page in range(1, total_pages + 1):
                # Simulate processing time
                await asyncio.sleep(2)
                
                # Update progress
                progress = int((page / total_pages) * 100)
                processing_tasks[document_id].update({
                    "currentPage": page,
                    "progress": progress,
                    "estimatedTimeRemaining": (total_pages - page) * 2,
                    "confidence": 85 + (page / total_pages * 10)
                })
            
            # Update database with completion
            async with session_manager._db_pool.acquire() as conn:
                await conn.execute("SET LOCAL app.current_ip_hash = $1", ip_hash)
                await conn.execute("""
                    UPDATE documents 
                    SET status = 'completed', 
                        completed_at = NOW(),
                        pages = $2,
                        ocr_confidence = $3,
                        processing_duration = NOW() - processing_started_at
                    WHERE document_id = $1
                """, document_id, total_pages, 92.5)
            
            # Mark as completed
            processing_tasks[document_id]["status"] = "completed"
            processing_tasks[document_id]["progress"] = 100
            
        finally:
            # Clean up temp file
            os.unlink(temp_pdf_path)
    
    except Exception as e:
        logger.error(f"OCR processing failed for {document_id}: {e}")
        processing_tasks[document_id]["status"] = "error"
        
        # Update database
        async with session_manager._db_pool.acquire() as conn:
            await conn.execute("SET LOCAL app.current_ip_hash = $1", ip_hash)
            await conn.execute("""
                UPDATE documents 
                SET status = 'error', error_message = $2
                WHERE document_id = $1
            """, document_id, str(e))

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        access_log=True
    )