"""
BOCRA Secure File Storage System with IP-based Isolation
Handles encrypted, compressed file storage with complete isolation between IP addresses
"""

import os
import gzip
import hashlib
import secrets
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, BinaryIO, Tuple
from dataclasses import dataclass
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import json
import logging

logger = logging.getLogger(__name__)

@dataclass
class StoredDocument:
    """Represents a stored document with metadata"""
    document_id: str
    ip_hash: str
    filename: str
    file_hash: str
    storage_path: str
    original_size: int
    compressed_size: int
    encryption_key_id: str
    metadata: Dict[str, Any]
    created_at: datetime
    content_type: str = "application/pdf"

class SecureFileStorage:
    """Secure file storage with IP-based isolation and encryption"""
    
    def __init__(self, 
                 base_storage_path: str = "/var/bocra/secure_storage",
                 encryption_key: str = None,
                 compression_level: int = 6):
        
        self.base_storage_path = Path(base_storage_path)
        self.compression_level = compression_level
        
        # Ensure base directory exists
        self.base_storage_path.mkdir(parents=True, exist_ok=True, mode=0o700)
        
        # Initialize encryption
        self.master_key = encryption_key or os.getenv('BOCRA_STORAGE_KEY', self._generate_master_key())
        self._cipher = self._create_cipher(self.master_key)
        
        # Create subdirectories
        self._ensure_directories()
    
    def _generate_master_key(self) -> str:
        """Generate a secure master key for encryption"""
        return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    
    def _create_cipher(self, key: str) -> Fernet:
        """Create Fernet cipher from master key"""
        # Derive key using PBKDF2
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'bocra_storage_salt',  # In production, use random salt per installation
            iterations=100000,
        )
        derived_key = base64.urlsafe_b64encode(kdf.derive(key.encode()))
        return Fernet(derived_key)
    
    def _ensure_directories(self):
        """Create necessary storage directories"""
        directories = [
            self.base_storage_path / "documents",
            self.base_storage_path / "metadata", 
            self.base_storage_path / "temp",
            self.base_storage_path / "quarantine"
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    
    def _get_ip_storage_path(self, ip_hash: str) -> Path:
        """Get storage directory path for specific IP hash"""
        # Use first 4 characters of hash for directory sharding
        shard = ip_hash[:4]
        ip_path = self.base_storage_path / "documents" / shard / ip_hash
        ip_path.mkdir(parents=True, exist_ok=True, mode=0o700)
        return ip_path
    
    def _get_metadata_path(self, ip_hash: str, document_id: str) -> Path:
        """Get metadata file path for document"""
        shard = ip_hash[:4]
        metadata_path = self.base_storage_path / "metadata" / shard / ip_hash
        metadata_path.mkdir(parents=True, exist_ok=True, mode=0o700)
        return metadata_path / f"{document_id}.json"
    
    def _calculate_file_hash(self, content: bytes) -> str:
        """Calculate SHA256 hash of file content"""
        return hashlib.sha256(content).hexdigest()
    
    def _compress_content(self, content: bytes) -> bytes:
        """Compress content using gzip"""
        return gzip.compress(content, compresslevel=self.compression_level)
    
    def _decompress_content(self, compressed_content: bytes) -> bytes:
        """Decompress gzip content"""
        return gzip.decompress(compressed_content)
    
    def _encrypt_content(self, content: bytes) -> bytes:
        """Encrypt content using Fernet"""
        return self._cipher.encrypt(content)
    
    def _decrypt_content(self, encrypted_content: bytes) -> bytes:
        """Decrypt content using Fernet"""
        return self._cipher.decrypt(encrypted_content)
    
    async def store_document(self, 
                           ip_hash: str,
                           document_id: str,
                           filename: str,
                           content: bytes,
                           metadata: Dict[str, Any] = None) -> StoredDocument:
        """Store a document with encryption and compression"""
        try:
            # Calculate file hash for deduplication and integrity
            file_hash = self._calculate_file_hash(content)
            original_size = len(content)
            
            # Check for duplicate files for this IP
            existing_doc = await self._find_existing_document(ip_hash, file_hash)
            if existing_doc:
                logger.info(f"Document already exists for IP {ip_hash[:8]}...")
                return existing_doc
            
            # Compress content
            compressed_content = self._compress_content(content)
            compressed_size = len(compressed_content)
            
            # Encrypt compressed content
            encrypted_content = self._encrypt_content(compressed_content)
            
            # Get storage path
            storage_dir = self._get_ip_storage_path(ip_hash)
            storage_filename = f"{document_id}_{file_hash[:16]}.enc"
            storage_path = storage_dir / storage_filename
            
            # Write encrypted file
            with open(storage_path, 'wb') as f:
                f.write(encrypted_content)
            
            # Set restrictive permissions
            storage_path.chmod(0o600)
            
            # Create document metadata
            stored_doc = StoredDocument(
                document_id=document_id,
                ip_hash=ip_hash,
                filename=filename,
                file_hash=file_hash,
                storage_path=str(storage_path),
                original_size=original_size,
                compressed_size=compressed_size,
                encryption_key_id="master",  # In production, use key rotation
                metadata=metadata or {},
                created_at=datetime.now(timezone.utc)
            )
            
            # Store metadata
            await self._store_metadata(stored_doc)
            
            logger.info(f"Stored document {document_id} for IP {ip_hash[:8]}... "
                       f"(compressed: {compressed_size}/{original_size} bytes)")
            
            return stored_doc
        
        except Exception as e:
            logger.error(f"Error storing document {document_id}: {e}")
            raise
    
    async def retrieve_document(self, 
                              ip_hash: str,
                              document_id: str) -> Optional[Tuple[StoredDocument, bytes]]:
        """Retrieve and decrypt a document for specific IP"""
        try:
            # Load metadata
            metadata_path = self._get_metadata_path(ip_hash, document_id)
            if not metadata_path.exists():
                return None
            
            with open(metadata_path, 'r') as f:
                metadata_dict = json.load(f)
            
            # Verify IP hash matches (security check)
            if metadata_dict['ip_hash'] != ip_hash:
                logger.warning(f"IP hash mismatch for document {document_id}")
                return None
            
            # Create StoredDocument object
            stored_doc = StoredDocument(**metadata_dict)
            
            # Read encrypted file
            storage_path = Path(stored_doc.storage_path)
            if not storage_path.exists():
                logger.error(f"Storage file not found: {storage_path}")
                return None
            
            with open(storage_path, 'rb') as f:
                encrypted_content = f.read()
            
            # Decrypt and decompress
            compressed_content = self._decrypt_content(encrypted_content)
            original_content = self._decompress_content(compressed_content)
            
            # Verify integrity
            calculated_hash = self._calculate_file_hash(original_content)
            if calculated_hash != stored_doc.file_hash:
                logger.error(f"File integrity check failed for document {document_id}")
                return None
            
            logger.info(f"Retrieved document {document_id} for IP {ip_hash[:8]}...")
            return stored_doc, original_content
        
        except Exception as e:
            logger.error(f"Error retrieving document {document_id}: {e}")
            return None
    
    async def delete_document(self, ip_hash: str, document_id: str) -> bool:
        """Securely delete a document and its metadata"""
        try:
            # Load metadata to get storage path
            metadata_path = self._get_metadata_path(ip_hash, document_id)
            if not metadata_path.exists():
                return False
            
            with open(metadata_path, 'r') as f:
                metadata_dict = json.load(f)
            
            # Verify IP hash matches
            if metadata_dict['ip_hash'] != ip_hash:
                logger.warning(f"IP hash mismatch for document deletion {document_id}")
                return False
            
            storage_path = Path(metadata_dict['storage_path'])
            
            # Secure deletion: overwrite file before deletion
            if storage_path.exists():
                # Overwrite with random data
                file_size = storage_path.stat().st_size
                with open(storage_path, 'r+b') as f:
                    f.write(secrets.token_bytes(file_size))
                    f.flush()
                    os.fsync(f.fileno())
                
                # Delete file
                storage_path.unlink()
            
            # Delete metadata
            metadata_path.unlink()
            
            logger.info(f"Deleted document {document_id} for IP {ip_hash[:8]}...")
            return True
        
        except Exception as e:
            logger.error(f"Error deleting document {document_id}: {e}")
            return False
    
    async def list_documents(self, ip_hash: str) -> List[StoredDocument]:
        """List all documents for a specific IP hash"""
        try:
            documents = []
            
            # Get metadata directory for this IP
            shard = ip_hash[:4]
            metadata_dir = self.base_storage_path / "metadata" / shard / ip_hash
            
            if not metadata_dir.exists():
                return documents
            
            # Read all metadata files
            for metadata_file in metadata_dir.glob("*.json"):
                try:
                    with open(metadata_file, 'r') as f:
                        metadata_dict = json.load(f)
                    
                    # Verify IP hash
                    if metadata_dict['ip_hash'] == ip_hash:
                        # Convert datetime strings back to datetime objects
                        metadata_dict['created_at'] = datetime.fromisoformat(
                            metadata_dict['created_at'].replace('Z', '+00:00')
                        )
                        documents.append(StoredDocument(**metadata_dict))
                
                except Exception as e:
                    logger.error(f"Error reading metadata file {metadata_file}: {e}")
                    continue
            
            # Sort by creation time (newest first)
            documents.sort(key=lambda x: x.created_at, reverse=True)
            
            return documents
        
        except Exception as e:
            logger.error(f"Error listing documents for IP {ip_hash[:8]}...: {e}")
            return []
    
    async def get_storage_stats(self, ip_hash: str) -> Dict[str, Any]:
        """Get storage statistics for an IP hash"""
        try:
            documents = await self.list_documents(ip_hash)
            
            total_original_size = sum(doc.original_size for doc in documents)
            total_compressed_size = sum(doc.compressed_size for doc in documents)
            total_documents = len(documents)
            
            # Calculate storage efficiency
            compression_ratio = (total_compressed_size / total_original_size * 100) if total_original_size > 0 else 0
            
            return {
                'ip_hash': ip_hash,
                'total_documents': total_documents,
                'total_original_bytes': total_original_size,
                'total_storage_bytes': total_compressed_size,
                'compression_ratio_percent': round(compression_ratio, 2),
                'space_saved_bytes': total_original_size - total_compressed_size,
                'space_saved_percent': round(100 - compression_ratio, 2) if total_original_size > 0 else 0
            }
        
        except Exception as e:
            logger.error(f"Error getting storage stats for IP {ip_hash[:8]}...: {e}")
            return {}
    
    async def _store_metadata(self, stored_doc: StoredDocument):
        """Store document metadata as JSON"""
        metadata_path = self._get_metadata_path(stored_doc.ip_hash, stored_doc.document_id)
        
        metadata_dict = {
            'document_id': stored_doc.document_id,
            'ip_hash': stored_doc.ip_hash,
            'filename': stored_doc.filename,
            'file_hash': stored_doc.file_hash,
            'storage_path': stored_doc.storage_path,
            'original_size': stored_doc.original_size,
            'compressed_size': stored_doc.compressed_size,
            'encryption_key_id': stored_doc.encryption_key_id,
            'metadata': stored_doc.metadata,
            'created_at': stored_doc.created_at.isoformat(),
            'content_type': stored_doc.content_type
        }
        
        with open(metadata_path, 'w') as f:
            json.dump(metadata_dict, f, indent=2)
        
        metadata_path.chmod(0o600)
    
    async def _find_existing_document(self, ip_hash: str, file_hash: str) -> Optional[StoredDocument]:
        """Find existing document with same file hash for this IP"""
        documents = await self.list_documents(ip_hash)
        for doc in documents:
            if doc.file_hash == file_hash:
                return doc
        return None
    
    async def cleanup_temp_files(self, max_age_hours: int = 24) -> int:
        """Clean up temporary files older than max_age_hours"""
        try:
            temp_dir = self.base_storage_path / "temp"
            if not temp_dir.exists():
                return 0
            
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
            cleaned_count = 0
            
            for temp_file in temp_dir.iterdir():
                if temp_file.is_file():
                    file_mtime = datetime.fromtimestamp(temp_file.stat().st_mtime, timezone.utc)
                    if file_mtime < cutoff_time:
                        temp_file.unlink()
                        cleaned_count += 1
            
            logger.info(f"Cleaned up {cleaned_count} temporary files")
            return cleaned_count
        
        except Exception as e:
            logger.error(f"Error cleaning up temp files: {e}")
            return 0
    
    async def verify_storage_integrity(self, ip_hash: str) -> Dict[str, Any]:
        """Verify storage integrity for an IP hash"""
        try:
            documents = await self.list_documents(ip_hash)
            results = {
                'total_documents': len(documents),
                'verified_documents': 0,
                'corrupt_documents': 0,
                'missing_files': 0,
                'corrupt_files': []
            }
            
            for doc in documents:
                storage_path = Path(doc.storage_path)
                
                if not storage_path.exists():
                    results['missing_files'] += 1
                    results['corrupt_files'].append({
                        'document_id': doc.document_id,
                        'filename': doc.filename,
                        'issue': 'Storage file missing'
                    })
                    continue
                
                try:
                    # Try to retrieve and verify
                    retrieved = await self.retrieve_document(ip_hash, doc.document_id)
                    if retrieved:
                        results['verified_documents'] += 1
                    else:
                        results['corrupt_documents'] += 1
                        results['corrupt_files'].append({
                            'document_id': doc.document_id,
                            'filename': doc.filename,
                            'issue': 'Decryption or integrity check failed'
                        })
                
                except Exception as e:
                    results['corrupt_documents'] += 1
                    results['corrupt_files'].append({
                        'document_id': doc.document_id,
                        'filename': doc.filename,
                        'issue': str(e)
                    })
            
            results['integrity_percentage'] = (
                results['verified_documents'] / results['total_documents'] * 100
                if results['total_documents'] > 0 else 100
            )
            
            return results
        
        except Exception as e:
            logger.error(f"Error verifying storage integrity: {e}")
            return {'error': str(e)}

# Usage example and testing
async def test_secure_storage():
    """Test the secure storage functionality"""
    storage = SecureFileStorage("/tmp/bocra_test_storage")
    
    # Test data
    ip_hash = "test_ip_hash_12345"
    document_id = "doc_123"
    filename = "test_document.pdf"
    content = b"This is test PDF content for BOCRA secure storage"
    metadata = {"pages": 5, "language": "eng", "dpi": 300}
    
    try:
        # Test storage
        stored_doc = await storage.store_document(ip_hash, document_id, filename, content, metadata)
        print(f"Stored document: {stored_doc.document_id}")
        
        # Test retrieval
        retrieved = await storage.retrieve_document(ip_hash, document_id)
        if retrieved:
            doc, retrieved_content = retrieved
            print(f"Retrieved document: {doc.filename}, Content match: {content == retrieved_content}")
        
        # Test listing
        documents = await storage.list_documents(ip_hash)
        print(f"Documents for IP: {len(documents)}")
        
        # Test stats
        stats = await storage.get_storage_stats(ip_hash)
        print(f"Storage stats: {stats}")
        
        # Test integrity check
        integrity = await storage.verify_storage_integrity(ip_hash)
        print(f"Integrity check: {integrity}")
        
        # Test deletion
        deleted = await storage.delete_document(ip_hash, document_id)
        print(f"Document deleted: {deleted}")
        
    except Exception as e:
        print(f"Test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_secure_storage())