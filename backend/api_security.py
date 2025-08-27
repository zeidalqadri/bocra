"""
BOCRA API Security Layer with IP-based Authentication
Provides middleware and decorators for securing API endpoints with IP isolation
"""

import asyncio
import functools
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Callable, Tuple
from dataclasses import dataclass
from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import redis.asyncio as redis
import logging
from ipaddress import ip_address, AddressValueError

from .session_manager import SessionManager, UserSession

logger = logging.getLogger(__name__)

@dataclass
class SecurityContext:
    """Security context for authenticated requests"""
    ip_address: str
    ip_hash: str
    session: UserSession
    user_agent: Optional[str] = None
    request_id: Optional[str] = None

class IPSecurityMiddleware:
    """Middleware for IP-based authentication and rate limiting"""
    
    def __init__(self, 
                 session_manager: SessionManager,
                 redis_client: redis.Redis,
                 rate_limit_requests: int = 100,
                 rate_limit_window: int = 3600,  # 1 hour
                 suspicious_threshold: int = 1000):
        
        self.session_manager = session_manager
        self.redis_client = redis_client
        self.rate_limit_requests = rate_limit_requests
        self.rate_limit_window = rate_limit_window
        self.suspicious_threshold = suspicious_threshold
        
        # Security bearer for token authentication
        self.bearer = HTTPBearer(auto_error=False)
    
    def get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request headers"""
        # Check for forwarded IP headers (for reverse proxy setups)
        forwarded_ips = [
            request.headers.get("x-forwarded-for"),
            request.headers.get("x-real-ip"),
            request.headers.get("cf-connecting-ip"),  # Cloudflare
            request.headers.get("x-client-ip")
        ]
        
        for forwarded_ip in forwarded_ips:
            if forwarded_ip:
                # Take first IP if comma-separated list
                ip = forwarded_ip.split(',')[0].strip()
                try:
                    # Validate IP address
                    ip_address(ip)
                    return ip
                except AddressValueError:
                    continue
        
        # Fall back to direct client IP
        if request.client and request.client.host:
            return request.client.host
        
        # Default fallback
        return "127.0.0.1"
    
    async def check_rate_limit(self, ip_hash: str) -> Tuple[bool, Dict[str, Any]]:
        """Check rate limiting for IP hash"""
        try:
            current_time = int(datetime.now(timezone.utc).timestamp())
            window_start = current_time - self.rate_limit_window
            
            # Use Redis sorted set for sliding window rate limiting
            key = f"rate_limit:{ip_hash}"
            
            # Remove expired entries
            await self.redis_client.zremrangebyscore(key, 0, window_start)
            
            # Count current requests in window
            current_requests = await self.redis_client.zcard(key)
            
            # Check if over limit
            if current_requests >= self.rate_limit_requests:
                # Get oldest request time for reset calculation
                oldest = await self.redis_client.zrange(key, 0, 0, withscores=True)
                reset_time = int(oldest[0][1]) + self.rate_limit_window if oldest else current_time + self.rate_limit_window
                
                return False, {
                    'requests_made': current_requests,
                    'requests_limit': self.rate_limit_requests,
                    'window_seconds': self.rate_limit_window,
                    'reset_time': reset_time
                }
            
            # Add current request
            await self.redis_client.zadd(key, {str(current_time): current_time})
            await self.redis_client.expire(key, self.rate_limit_window)
            
            return True, {
                'requests_made': current_requests + 1,
                'requests_limit': self.rate_limit_requests,
                'window_seconds': self.rate_limit_window,
                'reset_time': current_time + self.rate_limit_window
            }
        
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            # Allow request on error (fail open)
            return True, {}
    
    async def detect_suspicious_activity(self, ip_hash: str, request: Request) -> bool:
        """Detect suspicious activity patterns"""
        try:
            current_time = int(datetime.now(timezone.utc).timestamp())
            
            # Check for rapid requests (potential bot/attack)
            rapid_key = f"rapid_requests:{ip_hash}"
            rapid_count = await self.redis_client.incr(rapid_key)
            await self.redis_client.expire(rapid_key, 60)  # 1 minute window
            
            if rapid_count > 60:  # More than 60 requests per minute
                await self._log_security_event(ip_hash, "RAPID_REQUESTS", {
                    "requests_per_minute": rapid_count,
                    "user_agent": request.headers.get("user-agent", ""),
                    "path": str(request.url)
                })
                return True
            
            # Check for suspicious user agents
            user_agent = request.headers.get("user-agent", "").lower()
            suspicious_agents = [
                "bot", "crawler", "spider", "scraper", "curl", "wget", "python", "go-http"
            ]
            
            if any(agent in user_agent for agent in suspicious_agents):
                await self._log_security_event(ip_hash, "SUSPICIOUS_USER_AGENT", {
                    "user_agent": user_agent,
                    "path": str(request.url)
                })
                return True
            
            # Check for path traversal attempts
            path = str(request.url.path).lower()
            suspicious_patterns = ["../", "..\\", "/etc/", "/proc/", "cmd=", "exec="]
            
            if any(pattern in path for pattern in suspicious_patterns):
                await self._log_security_event(ip_hash, "PATH_TRAVERSAL_ATTEMPT", {
                    "path": str(request.url),
                    "user_agent": user_agent
                })
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"Error detecting suspicious activity: {e}")
            return False
    
    async def _log_security_event(self, ip_hash: str, event_type: str, details: Dict[str, Any]):
        """Log security events"""
        try:
            event_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "ip_hash": ip_hash,
                "event_type": event_type,
                "details": details
            }
            
            # Store in Redis for immediate analysis
            await self.redis_client.lpush(
                "security_events",
                f"{event_type}:{ip_hash}:{int(datetime.now(timezone.utc).timestamp())}"
            )
            await self.redis_client.ltrim("security_events", 0, 9999)  # Keep last 10k events
            
            logger.warning(f"Security event: {event_type} for IP {ip_hash[:8]}... - {details}")
        
        except Exception as e:
            logger.error(f"Error logging security event: {e}")

# Dependency for FastAPI authentication
async def authenticate_request(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    security_middleware: IPSecurityMiddleware = Depends()
) -> SecurityContext:
    """FastAPI dependency for request authentication"""
    
    # Extract client IP
    client_ip = security_middleware.get_client_ip(request)
    ip_hash = security_middleware.session_manager.hash_ip_address(client_ip)
    
    # Check rate limiting
    rate_limit_ok, rate_info = await security_middleware.check_rate_limit(ip_hash)
    if not rate_limit_ok:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "X-RateLimit-Limit": str(rate_info.get('requests_limit', 0)),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(rate_info.get('reset_time', 0))
            }
        )
    
    # Check for suspicious activity
    if await security_middleware.detect_suspicious_activity(ip_hash, request):
        raise HTTPException(
            status_code=403,
            detail="Suspicious activity detected"
        )
    
    # Verify session token if provided
    session = None
    if credentials and credentials.credentials:
        session = await security_middleware.session_manager.validate_session(credentials.credentials)
        
        if not session:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired session token"
            )
        
        # Verify IP matches session
        if session.ip_hash != ip_hash:
            await security_middleware._log_security_event(ip_hash, "IP_MISMATCH", {
                "session_ip_hash": session.ip_hash,
                "request_ip_hash": ip_hash
            })
            raise HTTPException(
                status_code=403,
                detail="IP address mismatch"
            )
    
    # For endpoints that don't require authentication, create session automatically
    if not session:
        user_agent = request.headers.get("user-agent")
        session = await security_middleware.session_manager.create_session(client_ip, user_agent)
    
    return SecurityContext(
        ip_address=client_ip,
        ip_hash=ip_hash,
        session=session,
        user_agent=request.headers.get("user-agent"),
        request_id=request.headers.get("x-request-id")
    )

# Decorator for securing functions
def require_authentication(func: Callable) -> Callable:
    """Decorator to require valid session authentication"""
    @functools.wraps(func)
    async def wrapper(security_context: SecurityContext = Depends(authenticate_request), *args, **kwargs):
        if not security_context.session or not security_context.session.is_active:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Add security context to kwargs
        kwargs['security_context'] = security_context
        return await func(*args, **kwargs)
    
    return wrapper

def ip_isolated(func: Callable) -> Callable:
    """Decorator to ensure IP isolation for data access"""
    @functools.wraps(func)
    async def wrapper(security_context: SecurityContext = Depends(authenticate_request), *args, **kwargs):
        # Set the IP context for database queries
        kwargs['ip_hash'] = security_context.ip_hash
        kwargs['security_context'] = security_context
        return await func(*args, **kwargs)
    
    return wrapper

class SecurityAuditLogger:
    """Audit logger for security events"""
    
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
    
    async def log_access_attempt(self, 
                               security_context: SecurityContext,
                               endpoint: str,
                               success: bool,
                               details: Dict[str, Any] = None):
        """Log API access attempts"""
        await self.session_manager._log_audit_event(
            security_context.ip_hash,
            security_context.ip_address,
            "API_ACCESS" if success else "API_ACCESS_DENIED",
            {
                "endpoint": endpoint,
                "user_agent": security_context.user_agent,
                "request_id": security_context.request_id,
                "details": details or {}
            }
        )
    
    async def log_document_access(self,
                                security_context: SecurityContext,
                                document_id: str,
                                action: str,
                                success: bool,
                                details: Dict[str, Any] = None):
        """Log document access events"""
        await self.session_manager._log_audit_event(
            security_context.ip_hash,
            security_context.ip_address,
            f"DOCUMENT_{action.upper()}" + ("" if success else "_FAILED"),
            {
                "document_id": document_id,
                "action": action,
                "user_agent": security_context.user_agent,
                "request_id": security_context.request_id,
                "details": details or {}
            }
        )

# Custom exception for security violations
class SecurityViolationException(Exception):
    """Exception raised for security policy violations"""
    def __init__(self, message: str, violation_type: str, details: Dict[str, Any] = None):
        self.message = message
        self.violation_type = violation_type
        self.details = details or {}
        super().__init__(self.message)

# Security policy enforcement
class SecurityPolicy:
    """Enforces security policies and constraints"""
    
    def __init__(self,
                 max_documents_per_ip: int = 1000,
                 max_storage_bytes_per_ip: int = 10 * 1024 * 1024 * 1024,  # 10GB
                 max_file_size_bytes: int = 100 * 1024 * 1024,  # 100MB
                 allowed_file_types: list = None):
        
        self.max_documents_per_ip = max_documents_per_ip
        self.max_storage_bytes_per_ip = max_storage_bytes_per_ip
        self.max_file_size_bytes = max_file_size_bytes
        self.allowed_file_types = allowed_file_types or ['.pdf']
    
    async def check_upload_policy(self, 
                                security_context: SecurityContext,
                                filename: str,
                                file_size: int,
                                current_documents: int,
                                current_storage_bytes: int):
        """Check if upload is allowed under security policy"""
        
        # Check file size
        if file_size > self.max_file_size_bytes:
            raise SecurityViolationException(
                f"File too large: {file_size} bytes (max: {self.max_file_size_bytes})",
                "FILE_SIZE_EXCEEDED",
                {"file_size": file_size, "max_size": self.max_file_size_bytes}
            )
        
        # Check file type
        file_ext = '.' + filename.split('.')[-1].lower() if '.' in filename else ''
        if file_ext not in self.allowed_file_types:
            raise SecurityViolationException(
                f"File type not allowed: {file_ext}",
                "FILE_TYPE_NOT_ALLOWED",
                {"file_extension": file_ext, "allowed_types": self.allowed_file_types}
            )
        
        # Check document count limit
        if current_documents >= self.max_documents_per_ip:
            raise SecurityViolationException(
                f"Document limit reached: {current_documents} (max: {self.max_documents_per_ip})",
                "DOCUMENT_LIMIT_EXCEEDED",
                {"current_count": current_documents, "max_count": self.max_documents_per_ip}
            )
        
        # Check storage limit
        if current_storage_bytes + file_size > self.max_storage_bytes_per_ip:
            raise SecurityViolationException(
                f"Storage limit exceeded: {current_storage_bytes + file_size} bytes (max: {self.max_storage_bytes_per_ip})",
                "STORAGE_LIMIT_EXCEEDED",
                {"current_storage": current_storage_bytes, "file_size": file_size, "max_storage": self.max_storage_bytes_per_ip}
            )

# Usage example for FastAPI integration
"""
from fastapi import FastAPI, Depends
from .api_security import authenticate_request, require_authentication, ip_isolated, SecurityContext

app = FastAPI()

@app.get("/api/documents")
@ip_isolated
async def list_documents(security_context: SecurityContext = Depends(authenticate_request)):
    # Documents will be automatically filtered by IP hash
    # security_context.ip_hash is available for database queries
    pass

@app.post("/api/documents/upload")
@require_authentication
async def upload_document(security_context: SecurityContext = Depends(authenticate_request)):
    # Requires valid session token
    # IP isolation is automatically enforced
    pass

@app.get("/api/documents/{document_id}")
@ip_isolated
async def get_document(document_id: str, security_context: SecurityContext = Depends(authenticate_request)):
    # Document access is automatically IP-isolated
    pass
"""