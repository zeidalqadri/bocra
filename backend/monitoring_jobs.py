"""
BOCRA Monitoring and Cleanup Jobs
Background tasks for system maintenance, monitoring, and security
"""

import asyncio
import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import asyncpg
import redis.asyncio as redis
from pathlib import Path

from .session_manager import SessionManager
from .secure_storage import SecureFileStorage

logger = logging.getLogger(__name__)

@dataclass
class SystemMetrics:
    """System health and performance metrics"""
    timestamp: datetime
    active_sessions: int
    total_documents: int
    total_storage_bytes: int
    processing_queue_length: int
    average_processing_time: float
    error_rate_percent: float
    disk_usage_percent: float
    memory_usage_percent: float

@dataclass
class SecurityAlert:
    """Security alert information"""
    timestamp: datetime
    alert_type: str
    severity: str
    ip_hash: str
    details: Dict[str, Any]
    resolved: bool = False

class MonitoringService:
    """System monitoring and alerting service"""
    
    def __init__(self, 
                 session_manager: SessionManager,
                 secure_storage: SecureFileStorage,
                 redis_client: redis.Redis,
                 alert_thresholds: Dict[str, Any] = None):
        
        self.session_manager = session_manager
        self.secure_storage = secure_storage
        self.redis_client = redis_client
        
        # Default alert thresholds
        self.alert_thresholds = alert_thresholds or {
            'disk_usage_percent': 85.0,
            'memory_usage_percent': 90.0,
            'error_rate_percent': 10.0,
            'processing_queue_length': 100,
            'session_count': 1000,
            'rapid_requests_per_minute': 60,
            'failed_logins_per_hour': 50
        }
        
        self.alerts: List[SecurityAlert] = []
    
    async def collect_system_metrics(self) -> SystemMetrics:
        """Collect comprehensive system metrics"""
        try:
            current_time = datetime.now(timezone.utc)
            
            # Database metrics
            async with self.session_manager._db_pool.acquire() as conn:
                # Active sessions
                active_sessions = await conn.fetchval(
                    "SELECT COUNT(*) FROM user_sessions WHERE is_active = true AND expires_at > NOW()"
                )
                
                # Total documents
                total_documents = await conn.fetchval(
                    "SELECT COUNT(*) FROM documents"
                )
                
                # Total storage
                total_storage = await conn.fetchval(
                    "SELECT COALESCE(SUM(original_size), 0) FROM documents"
                )
                
                # Processing queue
                queue_length = await conn.fetchval(
                    "SELECT COUNT(*) FROM processing_queue WHERE worker_id IS NULL"
                )
                
                # Average processing time (last 24 hours)
                avg_processing_time = await conn.fetchval("""
                    SELECT COALESCE(AVG(EXTRACT(EPOCH FROM processing_duration)), 0)
                    FROM documents 
                    WHERE status = 'completed' 
                    AND completed_at > NOW() - INTERVAL '24 hours'
                """)
                
                # Error rate (last hour)
                total_recent = await conn.fetchval("""
                    SELECT COUNT(*) FROM documents 
                    WHERE created_at > NOW() - INTERVAL '1 hour'
                """)
                
                error_recent = await conn.fetchval("""
                    SELECT COUNT(*) FROM documents 
                    WHERE status = 'error' 
                    AND created_at > NOW() - INTERVAL '1 hour'
                """)
                
                error_rate = (error_recent / total_recent * 100) if total_recent > 0 else 0
            
            # System resource metrics (simplified - would use psutil in production)
            disk_usage = await self._get_disk_usage()
            memory_usage = await self._get_memory_usage()
            
            return SystemMetrics(
                timestamp=current_time,
                active_sessions=active_sessions,
                total_documents=total_documents,
                total_storage_bytes=total_storage,
                processing_queue_length=queue_length,
                average_processing_time=avg_processing_time,
                error_rate_percent=error_rate,
                disk_usage_percent=disk_usage,
                memory_usage_percent=memory_usage
            )
        
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
            # Return default metrics on error
            return SystemMetrics(
                timestamp=datetime.now(timezone.utc),
                active_sessions=0,
                total_documents=0,
                total_storage_bytes=0,
                processing_queue_length=0,
                average_processing_time=0.0,
                error_rate_percent=0.0,
                disk_usage_percent=0.0,
                memory_usage_percent=0.0
            )
    
    async def _get_disk_usage(self) -> float:
        """Get disk usage percentage"""
        try:
            import shutil
            total, used, free = shutil.disk_usage("/")
            return (used / total) * 100
        except Exception:
            return 0.0
    
    async def _get_memory_usage(self) -> float:
        """Get memory usage percentage"""
        try:
            # Read from /proc/meminfo on Linux
            with open('/proc/meminfo', 'r') as f:
                meminfo = f.read()
            
            total_kb = int([line for line in meminfo.split('\n') if 'MemTotal' in line][0].split()[1])
            available_kb = int([line for line in meminfo.split('\n') if 'MemAvailable' in line][0].split()[1])
            
            used_kb = total_kb - available_kb
            return (used_kb / total_kb) * 100
        except Exception:
            return 0.0
    
    async def check_alert_thresholds(self, metrics: SystemMetrics) -> List[SecurityAlert]:
        """Check metrics against alert thresholds"""
        alerts = []
        
        # Disk usage alert
        if metrics.disk_usage_percent > self.alert_thresholds['disk_usage_percent']:
            alerts.append(SecurityAlert(
                timestamp=metrics.timestamp,
                alert_type="HIGH_DISK_USAGE",
                severity="WARNING",
                ip_hash="system",
                details={
                    "disk_usage_percent": metrics.disk_usage_percent,
                    "threshold": self.alert_thresholds['disk_usage_percent']
                }
            ))
        
        # Memory usage alert
        if metrics.memory_usage_percent > self.alert_thresholds['memory_usage_percent']:
            alerts.append(SecurityAlert(
                timestamp=metrics.timestamp,
                alert_type="HIGH_MEMORY_USAGE",
                severity="CRITICAL",
                ip_hash="system",
                details={
                    "memory_usage_percent": metrics.memory_usage_percent,
                    "threshold": self.alert_thresholds['memory_usage_percent']
                }
            ))
        
        # Error rate alert
        if metrics.error_rate_percent > self.alert_thresholds['error_rate_percent']:
            alerts.append(SecurityAlert(
                timestamp=metrics.timestamp,
                alert_type="HIGH_ERROR_RATE",
                severity="WARNING",
                ip_hash="system",
                details={
                    "error_rate_percent": metrics.error_rate_percent,
                    "threshold": self.alert_thresholds['error_rate_percent']
                }
            ))
        
        # Queue length alert
        if metrics.processing_queue_length > self.alert_thresholds['processing_queue_length']:
            alerts.append(SecurityAlert(
                timestamp=metrics.timestamp,
                alert_type="LARGE_PROCESSING_QUEUE",
                severity="WARNING",
                ip_hash="system",
                details={
                    "queue_length": metrics.processing_queue_length,
                    "threshold": self.alert_thresholds['processing_queue_length']
                }
            ))
        
        return alerts
    
    async def detect_security_anomalies(self) -> List[SecurityAlert]:
        """Detect security anomalies from Redis logs"""
        alerts = []
        current_time = datetime.now(timezone.utc)
        
        try:
            # Get recent security events
            events = await self.redis_client.lrange("security_events", 0, 999)
            
            # Count events by type and IP
            event_counts: Dict[str, Dict[str, int]] = {}
            
            for event in events:
                try:
                    parts = event.split(':', 2)
                    if len(parts) >= 3:
                        event_type, ip_hash, timestamp_str = parts
                        event_time = datetime.fromtimestamp(int(timestamp_str), timezone.utc)
                        
                        # Only consider events from last hour
                        if (current_time - event_time).total_seconds() <= 3600:
                            if event_type not in event_counts:
                                event_counts[event_type] = {}
                            if ip_hash not in event_counts[event_type]:
                                event_counts[event_type][ip_hash] = 0
                            event_counts[event_type][ip_hash] += 1
                
                except Exception as e:
                    logger.error(f"Error parsing security event: {event}, {e}")
                    continue
            
            # Check for anomalies
            for event_type, ip_counts in event_counts.items():
                for ip_hash, count in ip_counts.items():
                    
                    # Rapid requests anomaly
                    if event_type == "RAPID_REQUESTS" and count > self.alert_thresholds['rapid_requests_per_minute']:
                        alerts.append(SecurityAlert(
                            timestamp=current_time,
                            alert_type="RAPID_REQUESTS_ANOMALY",
                            severity="WARNING",
                            ip_hash=ip_hash,
                            details={
                                "event_count": count,
                                "threshold": self.alert_thresholds['rapid_requests_per_minute'],
                                "time_window": "1 hour"
                            }
                        ))
                    
                    # Failed login anomaly
                    if event_type == "AUTHENTICATION_FAILED" and count > self.alert_thresholds['failed_logins_per_hour']:
                        alerts.append(SecurityAlert(
                            timestamp=current_time,
                            alert_type="FAILED_LOGIN_ANOMALY",
                            severity="CRITICAL",
                            ip_hash=ip_hash,
                            details={
                                "failed_attempts": count,
                                "threshold": self.alert_thresholds['failed_logins_per_hour'],
                                "time_window": "1 hour"
                            }
                        ))
        
        except Exception as e:
            logger.error(f"Error detecting security anomalies: {e}")
        
        return alerts
    
    async def store_metrics(self, metrics: SystemMetrics):
        """Store metrics in database for historical analysis"""
        try:
            async with self.session_manager._db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO system_metrics (
                        timestamp, active_sessions, total_documents, total_storage_bytes,
                        processing_queue_length, average_processing_time, error_rate_percent,
                        disk_usage_percent, memory_usage_percent
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """, 
                    metrics.timestamp, metrics.active_sessions, metrics.total_documents,
                    metrics.total_storage_bytes, metrics.processing_queue_length,
                    metrics.average_processing_time, metrics.error_rate_percent,
                    metrics.disk_usage_percent, metrics.memory_usage_percent
                )
        except Exception as e:
            logger.error(f"Error storing metrics: {e}")

class CleanupService:
    """System cleanup and maintenance service"""
    
    def __init__(self, 
                 session_manager: SessionManager,
                 secure_storage: SecureFileStorage):
        
        self.session_manager = session_manager
        self.secure_storage = secure_storage
    
    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions"""
        try:
            count = await self.session_manager.cleanup_expired_sessions()
            logger.info(f"Cleaned up {count} expired sessions")
            return count
        except Exception as e:
            logger.error(f"Error cleaning up expired sessions: {e}")
            return 0
    
    async def cleanup_old_audit_logs(self, retention_days: int = 90) -> int:
        """Clean up old audit logs"""
        try:
            async with self.session_manager._db_pool.acquire() as conn:
                result = await conn.execute("""
                    DELETE FROM audit_log 
                    WHERE created_at < NOW() - $1::INTERVAL
                """, f"{retention_days} days")
                
                count = int(result.split()[-1]) if result.split() else 0
                logger.info(f"Cleaned up {count} old audit log entries")
                return count
        except Exception as e:
            logger.error(f"Error cleaning up audit logs: {e}")
            return 0
    
    async def cleanup_failed_documents(self, retention_hours: int = 24) -> int:
        """Clean up documents that failed processing"""
        try:
            async with self.session_manager._db_pool.acquire() as conn:
                # Get failed documents older than retention period
                failed_docs = await conn.fetch("""
                    SELECT document_id, ip_hash FROM documents
                    WHERE status = 'error' 
                    AND created_at < NOW() - $1::INTERVAL
                """, f"{retention_hours} hours")
                
                count = 0
                for doc in failed_docs:
                    # Clean up storage
                    success = await self.secure_storage.delete_document(
                        doc['ip_hash'], doc['document_id']
                    )
                    if success:
                        count += 1
                
                # Remove from database
                await conn.execute("""
                    DELETE FROM documents
                    WHERE status = 'error' 
                    AND created_at < NOW() - $1::INTERVAL
                """, f"{retention_hours} hours")
                
                logger.info(f"Cleaned up {count} failed documents")
                return count
        except Exception as e:
            logger.error(f"Error cleaning up failed documents: {e}")
            return 0
    
    async def cleanup_temp_files(self, max_age_hours: int = 24) -> int:
        """Clean up temporary files"""
        try:
            count = await self.secure_storage.cleanup_temp_files(max_age_hours)
            logger.info(f"Cleaned up {count} temporary files")
            return count
        except Exception as e:
            logger.error(f"Error cleaning up temp files: {e}")
            return 0
    
    async def optimize_database(self):
        """Perform database maintenance operations"""
        try:
            async with self.session_manager._db_pool.acquire() as conn:
                # Analyze tables for query optimization
                await conn.execute("ANALYZE;")
                
                # Vacuum to reclaim space
                await conn.execute("VACUUM;")
                
                logger.info("Database optimization completed")
        except Exception as e:
            logger.error(f"Error optimizing database: {e}")
    
    async def verify_storage_integrity(self) -> Dict[str, Any]:
        """Verify storage integrity across all users"""
        try:
            async with self.session_manager._db_pool.acquire() as conn:
                # Get all unique IP hashes
                ip_hashes = await conn.fetch("SELECT DISTINCT ip_hash FROM documents")
                
                total_results = {
                    'total_users_checked': 0,
                    'total_documents_verified': 0,
                    'total_corrupt_documents': 0,
                    'total_missing_files': 0,
                    'integrity_percentage': 100.0,
                    'corrupt_users': []
                }
                
                for row in ip_hashes:
                    ip_hash = row['ip_hash']
                    result = await self.secure_storage.verify_storage_integrity(ip_hash)
                    
                    total_results['total_users_checked'] += 1
                    total_results['total_documents_verified'] += result.get('verified_documents', 0)
                    total_results['total_corrupt_documents'] += result.get('corrupt_documents', 0)
                    total_results['total_missing_files'] += result.get('missing_files', 0)
                    
                    if result.get('corrupt_files'):
                        total_results['corrupt_users'].append({
                            'ip_hash': ip_hash[:8] + '...',
                            'corrupt_files': result['corrupt_files']
                        })
                
                # Calculate overall integrity
                total_docs = total_results['total_documents_verified'] + total_results['total_corrupt_documents']
                if total_docs > 0:
                    total_results['integrity_percentage'] = (
                        total_results['total_documents_verified'] / total_docs * 100
                    )
                
                logger.info(f"Storage integrity check completed: {total_results['integrity_percentage']:.1f}% integrity")
                return total_results
        
        except Exception as e:
            logger.error(f"Error verifying storage integrity: {e}")
            return {'error': str(e)}

class JobScheduler:
    """Task scheduler for background jobs"""
    
    def __init__(self, 
                 monitoring_service: MonitoringService,
                 cleanup_service: CleanupService):
        
        self.monitoring_service = monitoring_service
        self.cleanup_service = cleanup_service
        self.running = False
    
    async def start(self):
        """Start background job scheduler"""
        self.running = True
        logger.info("Starting background job scheduler")
        
        # Start concurrent tasks
        await asyncio.gather(
            self._metrics_collection_job(),
            self._security_monitoring_job(),
            self._cleanup_job(),
            self._integrity_check_job(),
            return_exceptions=True
        )
    
    async def stop(self):
        """Stop background job scheduler"""
        self.running = False
        logger.info("Stopping background job scheduler")
    
    async def _metrics_collection_job(self):
        """Collect system metrics every 5 minutes"""
        while self.running:
            try:
                metrics = await self.monitoring_service.collect_system_metrics()
                await self.monitoring_service.store_metrics(metrics)
                
                # Check for alerts
                alerts = await self.monitoring_service.check_alert_thresholds(metrics)
                for alert in alerts:
                    logger.warning(f"System Alert: {alert.alert_type} - {alert.details}")
                
            except Exception as e:
                logger.error(f"Error in metrics collection job: {e}")
            
            await asyncio.sleep(300)  # 5 minutes
    
    async def _security_monitoring_job(self):
        """Monitor security events every minute"""
        while self.running:
            try:
                alerts = await self.monitoring_service.detect_security_anomalies()
                for alert in alerts:
                    logger.warning(f"Security Alert: {alert.alert_type} for IP {alert.ip_hash[:8]}... - {alert.details}")
            
            except Exception as e:
                logger.error(f"Error in security monitoring job: {e}")
            
            await asyncio.sleep(60)  # 1 minute
    
    async def _cleanup_job(self):
        """Run cleanup tasks every hour"""
        while self.running:
            try:
                # Clean up expired sessions
                await self.cleanup_service.cleanup_expired_sessions()
                
                # Clean up old audit logs (daily at 2 AM)
                current_hour = datetime.now().hour
                if current_hour == 2:
                    await self.cleanup_service.cleanup_old_audit_logs()
                
                # Clean up failed documents
                await self.cleanup_service.cleanup_failed_documents()
                
                # Clean up temp files
                await self.cleanup_service.cleanup_temp_files()
                
                # Database optimization (weekly on Sunday at 3 AM)
                current_day = datetime.now().weekday()
                if current_day == 6 and current_hour == 3:  # Sunday at 3 AM
                    await self.cleanup_service.optimize_database()
            
            except Exception as e:
                logger.error(f"Error in cleanup job: {e}")
            
            await asyncio.sleep(3600)  # 1 hour
    
    async def _integrity_check_job(self):
        """Run storage integrity checks daily"""
        while self.running:
            try:
                current_hour = datetime.now().hour
                if current_hour == 4:  # 4 AM daily
                    result = await self.cleanup_service.verify_storage_integrity()
                    logger.info(f"Daily integrity check: {result}")
            
            except Exception as e:
                logger.error(f"Error in integrity check job: {e}")
            
            await asyncio.sleep(3600)  # Check every hour, but only run at 4 AM

# Usage example
async def main():
    """Example usage of monitoring and cleanup services"""
    # Initialize dependencies
    session_manager = SessionManager(
        database_url="postgresql://user:pass@localhost/bocra",
        redis_url="redis://localhost:6379"
    )
    await session_manager.initialize()
    
    secure_storage = SecureFileStorage("/var/bocra/secure_storage")
    
    redis_client = redis.from_url("redis://localhost:6379")
    
    # Initialize services
    monitoring_service = MonitoringService(session_manager, secure_storage, redis_client)
    cleanup_service = CleanupService(session_manager, secure_storage)
    
    # Start job scheduler
    scheduler = JobScheduler(monitoring_service, cleanup_service)
    
    try:
        await scheduler.start()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        await scheduler.stop()
        await session_manager.close()
        await redis_client.close()

if __name__ == "__main__":
    asyncio.run(main())