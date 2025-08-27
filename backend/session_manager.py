"""
BOCRA Session Manager with IP-based Isolation
Handles user sessions, IP hashing, and authentication for secure document access
"""

import hashlib
import secrets
import jwt
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from ipaddress import ip_address, IPv4Address, IPv6Address
import asyncpg
import redis.asyncio as redis
from cryptography.fernet import Fernet
import base64
import os
import logging

logger = logging.getLogger(__name__)

@dataclass
class UserSession:
    """Represents a user session with IP-based identification"""
    session_id: str
    ip_hash: str
    ip_address: str
    session_token: str
    created_at: datetime
    last_accessed: datetime
    expires_at: datetime
    is_active: bool
    user_agent: Optional[str] = None

class SessionManager:
    """Manages user sessions with IP-based isolation and security"""
    
    def __init__(self, 
                 database_url: str,
                 redis_url: str = "redis://localhost:6379",
                 secret_key: str = None,
                 session_duration_hours: int = 24,
                 ip_salt: str = None):
        
        self.database_url = database_url
        self.redis_url = redis_url
        self.secret_key = secret_key or os.getenv('BOCRA_SECRET_KEY', self._generate_secret())
        self.session_duration = timedelta(hours=session_duration_hours)
        self.ip_salt = ip_salt or os.getenv('BOCRA_IP_SALT', 'bocra_default_salt')
        
        # Connection pools
        self._db_pool: Optional[asyncpg.Pool] = None
        self._redis: Optional[redis.Redis] = None
        
        # Encryption for sensitive data
        key = base64.urlsafe_b64encode(hashlib.sha256(self.secret_key.encode()).digest())
        self._cipher = Fernet(key)
    
    async def initialize(self):
        """Initialize database and Redis connections"""
        try:
            # Initialize database connection pool
            self._db_pool = await asyncpg.create_pool(
                self.database_url,
                min_size=5,
                max_size=20,
                server_settings={'search_path': 'bocra_secure, public'}
            )
            
            # Initialize Redis connection
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()  # Test connection
            
            logger.info("Session manager initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize session manager: {e}")
            raise
    
    async def close(self):
        """Close all connections"""
        if self._db_pool:
            await self._db_pool.close()
        if self._redis:
            await self._redis.close()
    
    def _generate_secret(self) -> str:
        """Generate a secure random secret key"""
        return secrets.token_urlsafe(32)
    
    def hash_ip_address(self, ip_addr: str) -> str:
        """Hash IP address with salt for privacy while maintaining consistency"""
        try:
            # Validate IP address
            parsed_ip = ip_address(ip_addr)
            
            # Normalize IPv6 addresses
            if isinstance(parsed_ip, IPv6Address):
                normalized_ip = str(parsed_ip.compressed)
            else:
                normalized_ip = str(parsed_ip)
            
            # Hash with salt
            combined = f"{normalized_ip}{self.ip_salt}"
            return hashlib.sha256(combined.encode()).hexdigest()
        
        except ValueError as e:
            logger.error(f"Invalid IP address {ip_addr}: {e}")
            # Fallback hash for invalid IPs
            return hashlib.sha256(f"invalid_{ip_addr}{self.ip_salt}".encode()).hexdigest()
    
    def generate_session_token(self, ip_hash: str) -> str:
        """Generate a secure session token"""
        payload = {
            'ip_hash': ip_hash,
            'iat': datetime.utcnow(),
            'exp': datetime.utcnow() + self.session_duration,
            'jti': secrets.token_hex(16)  # JWT ID for uniqueness
        }
        return jwt.encode(payload, self.secret_key, algorithm='HS256')
    
    async def create_session(self, 
                           ip_address: str, 
                           user_agent: str = None) -> UserSession:
        """Create a new user session"""
        ip_hash = self.hash_ip_address(ip_address)
        session_token = self.generate_session_token(ip_hash)
        
        session = UserSession(
            session_id=secrets.token_urlsafe(32),
            ip_hash=ip_hash,
            ip_address=ip_address,
            session_token=session_token,
            created_at=datetime.now(timezone.utc),
            last_accessed=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + self.session_duration,
            is_active=True,
            user_agent=user_agent
        )
        
        async with self._db_pool.acquire() as conn:
            # Set the IP hash for RLS
            await conn.execute("SET LOCAL app.current_ip_hash = $1", ip_hash)
            
            # Ensure user exists in ip_users table
            await conn.execute("""
                INSERT INTO ip_users (ip_hash, first_seen, last_seen) 
                VALUES ($1, $2, $3)
                ON CONFLICT (ip_hash) DO UPDATE SET 
                    last_seen = $3,
                    updated_at = $3
            """, ip_hash, session.created_at, session.last_accessed)
            
            # Insert session
            await conn.execute("""
                INSERT INTO user_sessions (
                    session_id, ip_hash, session_token, ip_address,
                    user_agent, created_at, last_accessed, expires_at, is_active
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """, session.session_id, session.ip_hash, session.session_token,
                session.ip_address, session.user_agent, session.created_at,
                session.last_accessed, session.expires_at, session.is_active)
            
            # Cache session in Redis
            await self._cache_session(session)
            
            # Log session creation
            await self._log_audit_event(
                ip_hash, ip_address, "SESSION_CREATED", 
                {"session_id": session.session_id, "user_agent": user_agent}
            )
        
        logger.info(f"Created session for IP hash: {ip_hash[:8]}...")
        return session
    
    async def validate_session(self, session_token: str) -> Optional[UserSession]:
        """Validate a session token and return session if valid"""
        try:
            # Decode JWT token
            payload = jwt.decode(session_token, self.secret_key, algorithms=['HS256'])
            ip_hash = payload.get('ip_hash')
            
            if not ip_hash:
                return None
            
            # Check Redis cache first
            cached_session = await self._get_cached_session(session_token)
            if cached_session:
                return cached_session
            
            # Query database
            async with self._db_pool.acquire() as conn:
                await conn.execute("SET LOCAL app.current_ip_hash = $1", ip_hash)
                
                row = await conn.fetchrow("""
                    SELECT session_id, ip_hash, session_token, ip_address,
                           user_agent, created_at, last_accessed, expires_at, is_active
                    FROM user_sessions 
                    WHERE session_token = $1 AND is_active = true AND expires_at > NOW()
                """, session_token)
                
                if not row:
                    return None
                
                session = UserSession(**dict(row))
                
                # Update last accessed time
                await conn.execute("""
                    UPDATE user_sessions 
                    SET last_accessed = NOW() 
                    WHERE session_token = $1
                """, session_token)
                
                session.last_accessed = datetime.now(timezone.utc)
                
                # Update cache
                await self._cache_session(session)
                
                return session
        
        except jwt.ExpiredSignatureError:
            logger.info("Session token expired")
            await self._invalidate_session_by_token(session_token)
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid session token: {e}")
        except Exception as e:
            logger.error(f"Error validating session: {e}")
        
        return None
    
    async def invalidate_session(self, session_token: str) -> bool:
        """Invalidate a specific session"""
        try:
            payload = jwt.decode(session_token, self.secret_key, algorithms=['HS256'])
            ip_hash = payload.get('ip_hash')
            
            async with self._db_pool.acquire() as conn:
                await conn.execute("SET LOCAL app.current_ip_hash = $1", ip_hash)
                
                result = await conn.execute("""
                    UPDATE user_sessions 
                    SET is_active = false 
                    WHERE session_token = $1
                """, session_token)
                
                # Remove from Redis cache
                await self._redis.delete(f"session:{session_token}")
                
                # Log session invalidation
                await self._log_audit_event(
                    ip_hash, None, "SESSION_INVALIDATED",
                    {"session_token_hash": hashlib.sha256(session_token.encode()).hexdigest()[:8]}
                )
                
                return result == 'UPDATE 1'
        
        except Exception as e:
            logger.error(f"Error invalidating session: {e}")
            return False
    
    async def invalidate_all_sessions(self, ip_address: str) -> int:
        """Invalidate all sessions for a specific IP address"""
        ip_hash = self.hash_ip_address(ip_address)
        
        try:
            async with self._db_pool.acquire() as conn:
                await conn.execute("SET LOCAL app.current_ip_hash = $1", ip_hash)
                
                # Get all session tokens for removal from cache
                tokens = await conn.fetch("""
                    SELECT session_token FROM user_sessions 
                    WHERE ip_hash = $1 AND is_active = true
                """, ip_hash)
                
                # Invalidate in database
                result = await conn.execute("""
                    UPDATE user_sessions 
                    SET is_active = false 
                    WHERE ip_hash = $1 AND is_active = true
                """, ip_hash)
                
                # Remove from Redis cache
                for token_row in tokens:
                    await self._redis.delete(f"session:{token_row['session_token']}")
                
                count = int(result.split()[-1])
                
                # Log bulk session invalidation
                await self._log_audit_event(
                    ip_hash, ip_address, "ALL_SESSIONS_INVALIDATED",
                    {"sessions_invalidated": count}
                )
                
                return count
        
        except Exception as e:
            logger.error(f"Error invalidating all sessions: {e}")
            return 0
    
    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions from database and cache"""
        try:
            async with self._db_pool.acquire() as conn:
                # Get expired session tokens
                expired_tokens = await conn.fetch("""
                    SELECT session_token FROM user_sessions 
                    WHERE expires_at < NOW() OR is_active = false
                """)
                
                # Remove from database
                result = await conn.execute("""
                    DELETE FROM user_sessions 
                    WHERE expires_at < NOW() OR is_active = false
                """)
                
                # Remove from Redis cache
                for token_row in expired_tokens:
                    await self._redis.delete(f"session:{token_row['session_token']}")
                
                count = int(result.split()[-1]) if result.split() else 0
                logger.info(f"Cleaned up {count} expired sessions")
                return count
        
        except Exception as e:
            logger.error(f"Error cleaning up expired sessions: {e}")
            return 0
    
    async def get_user_info(self, ip_address: str) -> Dict[str, Any]:
        """Get user information and statistics by IP address"""
        ip_hash = self.hash_ip_address(ip_address)
        
        async with self._db_pool.acquire() as conn:
            await conn.execute("SET LOCAL app.current_ip_hash = $1", ip_hash)
            
            user_info = await conn.fetchrow("""
                SELECT 
                    ip_hash,
                    first_seen,
                    last_seen,
                    document_count,
                    total_pages_processed,
                    storage_used_bytes,
                    quota_limit_bytes,
                    settings,
                    is_active
                FROM ip_users 
                WHERE ip_hash = $1
            """, ip_hash)
            
            if not user_info:
                return None
            
            # Get active session count
            session_count = await conn.fetchval("""
                SELECT COUNT(*) FROM user_sessions 
                WHERE ip_hash = $1 AND is_active = true AND expires_at > NOW()
            """, ip_hash)
            
            result = dict(user_info)
            result['active_sessions'] = session_count
            result['quota_used_percent'] = round(
                (result['storage_used_bytes'] / result['quota_limit_bytes']) * 100, 2
            ) if result['quota_limit_bytes'] > 0 else 0
            
            return result
    
    async def update_user_settings(self, ip_address: str, settings: Dict[str, Any]) -> bool:
        """Update user settings"""
        ip_hash = self.hash_ip_address(ip_address)
        
        try:
            async with self._db_pool.acquire() as conn:
                await conn.execute("SET LOCAL app.current_ip_hash = $1", ip_hash)
                
                await conn.execute("""
                    UPDATE ip_users 
                    SET settings = settings || $2::jsonb,
                        updated_at = NOW()
                    WHERE ip_hash = $1
                """, ip_hash, settings)
                
                # Log settings update
                await self._log_audit_event(
                    ip_hash, ip_address, "SETTINGS_UPDATED",
                    {"updated_keys": list(settings.keys())}
                )
                
                return True
        
        except Exception as e:
            logger.error(f"Error updating user settings: {e}")
            return False
    
    async def _cache_session(self, session: UserSession):
        """Cache session in Redis"""
        session_data = {
            'session_id': session.session_id,
            'ip_hash': session.ip_hash,
            'ip_address': session.ip_address,
            'created_at': session.created_at.isoformat(),
            'last_accessed': session.last_accessed.isoformat(),
            'expires_at': session.expires_at.isoformat(),
            'is_active': str(session.is_active),
            'user_agent': session.user_agent or ''
        }
        
        ttl = int((session.expires_at - datetime.now(timezone.utc)).total_seconds())
        if ttl > 0:
            await self._redis.hmset(f"session:{session.session_token}", session_data)
            await self._redis.expire(f"session:{session.session_token}", ttl)
    
    async def _get_cached_session(self, session_token: str) -> Optional[UserSession]:
        """Get session from Redis cache"""
        try:
            cached_data = await self._redis.hgetall(f"session:{session_token}")
            
            if not cached_data:
                return None
            
            return UserSession(
                session_id=cached_data['session_id'],
                ip_hash=cached_data['ip_hash'],
                ip_address=cached_data['ip_address'],
                session_token=session_token,
                created_at=datetime.fromisoformat(cached_data['created_at']),
                last_accessed=datetime.fromisoformat(cached_data['last_accessed']),
                expires_at=datetime.fromisoformat(cached_data['expires_at']),
                is_active=cached_data['is_active'] == 'True',
                user_agent=cached_data.get('user_agent') or None
            )
        
        except Exception as e:
            logger.error(f"Error getting cached session: {e}")
            return None
    
    async def _invalidate_session_by_token(self, session_token: str):
        """Invalidate session by token (internal use)"""
        try:
            await self._redis.delete(f"session:{session_token}")
            # Database cleanup handled by cleanup job
        except Exception as e:
            logger.error(f"Error invalidating cached session: {e}")
    
    async def _log_audit_event(self, ip_hash: str, ip_address: str, action: str, details: Dict[str, Any]):
        """Log audit event"""
        try:
            async with self._db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO audit_log (ip_hash, ip_address, action, resource_type, details)
                    VALUES ($1, $2, $3, 'SESSION', $4)
                """, ip_hash, ip_address, action, details)
        except Exception as e:
            logger.error(f"Error logging audit event: {e}")

# Usage example and testing
async def test_session_manager():
    """Test the session manager functionality"""
    sm = SessionManager(
        database_url="postgresql://user:pass@localhost/bocra",
        redis_url="redis://localhost:6379",
        secret_key="test_secret_key_32_chars_long!",
        session_duration_hours=24
    )
    
    await sm.initialize()
    
    try:
        # Test session creation
        session = await sm.create_session("192.168.1.100", "Test User Agent")
        print(f"Created session: {session.session_id}")
        
        # Test session validation
        validated_session = await sm.validate_session(session.session_token)
        print(f"Validated session: {validated_session.session_id}")
        
        # Test user info
        user_info = await sm.get_user_info("192.168.1.100")
        print(f"User info: {user_info}")
        
        # Test session invalidation
        success = await sm.invalidate_session(session.session_token)
        print(f"Session invalidated: {success}")
        
    finally:
        await sm.close()

if __name__ == "__main__":
    asyncio.run(test_session_manager())