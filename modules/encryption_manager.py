"""Encryption management for memory data."""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
from pathlib import Path
from typing import Optional

LOGGER = logging.getLogger(__name__)

# Optional dependency
SQLCIPHER_AVAILABLE = False

try:
    import sqlcipher3
    SQLCIPHER_AVAILABLE = True
except ImportError:
    try:
        import pysqlcipher3.dbapi2 as sqlcipher3
        SQLCIPHER_AVAILABLE = True
    except ImportError:
        LOGGER.debug("sqlcipher3 not available; encryption disabled")


class EncryptionManager:
    """Manages encryption for sensitive data."""
    
    def __init__(self, key: Optional[str] = None) -> None:
        """Initialize encryption manager.
        
        Args:
            key: Encryption key (if None, will generate or load from env)
        """
        self._key = key or self._get_or_generate_key()
        self._is_available = SQLCIPHER_AVAILABLE
    
    def _get_or_generate_key(self) -> str:
        """Get encryption key from environment or generate one.
        
        Returns:
            Encryption key string
        """
        # Try to get from environment
        key = os.getenv("ENCRYPTION_KEY")
        if key:
            return key
        
        # Try to load from key file
        key_file = Path(os.getenv("SHIMEJI_STATE_DIR", Path.cwd() / "var")) / ".encryption_key"
        if key_file.exists():
            try:
                with open(key_file, "r") as f:
                    key = f.read().strip()
                    if key:
                        return key
            except Exception as exc:
                LOGGER.warning("Failed to read encryption key file: %s", exc)
        
        # Generate new key
        key = secrets.token_urlsafe(32)
        
        # Save to file
        try:
            key_file.parent.mkdir(parents=True, exist_ok=True)
            with open(key_file, "w") as f:
                f.write(key)
            # Set restrictive permissions
            os.chmod(key_file, 0o600)
            LOGGER.info("Generated new encryption key")
        except Exception as exc:
            LOGGER.warning("Failed to save encryption key: %s", exc)
        
        return key
    
    def is_available(self) -> bool:
        """Check if encryption is available.
        
        Returns:
            True if encryption is available
        """
        return self._is_available
    
    def get_encrypted_connection(self, db_path: Path) -> Optional[Any]:
        """Get encrypted SQLite connection.
        
        Args:
            db_path: Path to database file
        
        Returns:
            Encrypted connection or None if unavailable
        """
        if not self.is_available():
            return None
        
        try:
            conn = sqlcipher3.connect(str(db_path))
            # Set encryption key
            conn.execute(f"PRAGMA key='{self._key}'")
            return conn
        except Exception as exc:
            LOGGER.error("Failed to create encrypted connection: %s", exc)
            return None
    
    def encrypt_string(self, text: str) -> str:
        """Encrypt a string (simple implementation for non-database use).
        
        Args:
            text: Text to encrypt
        
        Returns:
            Encrypted string (hex encoded)
        """
        # Simple XOR encryption (not cryptographically secure, but simple)
        # For real encryption, use proper libraries like cryptography
        key_bytes = self._key.encode()[:len(text.encode())]
        text_bytes = text.encode()
        encrypted = bytes(a ^ b for a, b in zip(text_bytes, key_bytes * (len(text_bytes) // len(key_bytes) + 1)))
        return encrypted.hex()
    
    def decrypt_string(self, encrypted_hex: str) -> str:
        """Decrypt a string.
        
        Args:
            encrypted_hex: Encrypted string (hex encoded)
        
        Returns:
            Decrypted string
        """
        try:
            encrypted = bytes.fromhex(encrypted_hex)
            key_bytes = self._key.encode()[:len(encrypted)]
            decrypted = bytes(a ^ b for a, b in zip(encrypted, key_bytes * (len(encrypted) // len(key_bytes) + 1)))
            return decrypted.decode()
        except Exception as exc:
            LOGGER.error("Failed to decrypt string: %s", exc)
            return ""


