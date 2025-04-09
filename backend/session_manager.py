from threading import Lock
from typing import Optional, List
from datetime import datetime, timedelta
import json
import redis
from redis.exceptions import RedisError
from redis.connection import ConnectionPool
import os
import fcntl
import atexit
import time

from logging_config import StructuredLogger
logger = StructuredLogger(__name__)

class SessionManager:
    """Manages user sessions and conversation history using Redis as a backend.
    
    This class handles session creation, retrieval, and deletion, as well as
    managing conversation history for each session.
    """
    
    def __init__(self):
        """Initialize the SessionManager with Redis connection."""
        self._lock_fd = None
        self._pool = None
        self._redis = None
        self._lock_file = "/tmp/pipebot_redis.lock"
        self._config_file = "/tmp/pipebot_redis.json"
        self._initialization_timeout = 10  # seconds
        self._initialize_redis()

    def _initialize_redis(self):
        """Initialize Redis connection and connection pool."""
        try:
            # Create lock file if it doesn't exist
            if not os.path.exists(self._lock_file):
                with open(self._lock_file, 'w') as f:
                    f.write('')
            
            # Check if Redis is already initialized
            if os.path.exists(self._config_file):
                logger.info("Loading existing Redis configuration")
                self._load_redis_config()
                return

            # Try to acquire the lock file
            self._lock_fd = open(self._lock_file, 'r+')
            start_time = time.time()
            
            while True:
                try:
                    fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except IOError:
                    if time.time() - start_time > self._initialization_timeout:
                        logger.warning("Timeout waiting for Redis initialization, loading existing config")
                        if self._lock_fd:
                            try:
                                fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_UN)
                                self._lock_fd.close()
                            except Exception:
                                pass
                        self._load_redis_config()
                        return
                    time.sleep(0.1)

            # Initialize Redis if we have the lock
            if self._pool is None:
                logger.info("Initializing new Redis connection pool")
                self._pool = ConnectionPool(
                    host='localhost',
                    port=6379,
                    db=0,
                    decode_responses=True,
                    socket_timeout=5,
                    max_connections=20
                )
                # Test the pool with a temporary connection
                test_client = redis.Redis(connection_pool=self._pool)
                test_client.ping()
                test_client.close()
                logger.info("Redis connection pool initialized successfully")

                # Save the pool configuration
                self._save_redis_config()
            else:
                logger.info("Using existing Redis connection pool")
            
            # Create Redis client
            self._redis = redis.Redis(
                connection_pool=self._pool,
                socket_timeout=5,
                retry_on_timeout=True
            )
            logger.info("Created new Redis client")
            
            # Register cleanup
            atexit.register(self._cleanup)
            
        except RedisError as e:
            logger.error("Failed to connect to Redis", error=str(e))
            raise
        finally:
            if self._lock_fd:
                try:
                    fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_UN)
                    self._lock_fd.close()
                except Exception:
                    pass

    @property
    def redis(self):
        """Get the Redis client instance."""
        if not self._redis:
            raise RuntimeError("Redis client not initialized")
        return self._redis

    def _save_redis_config(self):
        """Save Redis configuration to file"""
        config = {
            'pool': {
                'host': 'localhost',
                'port': 6379,
                'db': 0,
                'decode_responses': True,
                'socket_timeout': 5,
                'max_connections': 20
            }
        }
        with open(self._config_file, 'w') as f:
            json.dump(config, f)
        logger.info("Redis configuration saved to file")

    def _load_redis_config(self):
        """Load Redis configuration from file"""
        try:
            with open(self._config_file, 'r') as f:
                config = json.load(f)
                self._pool = ConnectionPool(**config['pool'])
                self._redis = redis.Redis(
                    connection_pool=self._pool,
                    socket_timeout=5,
                    retry_on_timeout=True
                )
                logger.info("Redis configuration loaded from file")
        except Exception as e:
            logger.error("Failed to load Redis configuration", error=str(e))
            raise

    def _cleanup(self):
        """Cleanup resources"""
        if hasattr(self, '_lock_fd') and self._lock_fd:
            try:
                fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_UN)
                self._lock_fd.close()
            except Exception:
                pass

    def _serialize_session(self, session_data: dict) -> str:
        """Serialize session data to JSON string"""
        return json.dumps(session_data)

    def _deserialize_session(self, session_data: str) -> dict:
        """Deserialize session data from JSON string"""
        return json.loads(session_data)

    def create_session(self, session_id: str, user_data: dict) -> None:
        """Create a new session with user data"""
        try:
            # Acquire Redis lock for session operations
            lock_key = f"lock:session:{session_id}"
            if not self.redis.set(lock_key, "1", ex=5, nx=True):
                logger.warning("Could not acquire lock for session", session_id=session_id)
                return

            try:
                session_data = {
                    'user_data': user_data,
                    'created_at': datetime.utcnow().isoformat(),
                    'last_activity': datetime.utcnow().isoformat()
                }
                serialized_data = self._serialize_session(session_data)
                logger.info("Creating new session", session_id=session_id)
                
                # Use pipeline for atomic operations
                with self.redis.pipeline() as pipe:
                    pipe.set(
                        f"session:{session_id}",
                        serialized_data,
                        ex=86400  # 24 hours
                    )
                    pipe.set(
                        f"conversation:{session_id}",
                        json.dumps([]),
                        ex=86400  # 24 hours
                    )
                    pipe.execute()
                
                # Verify the session was created
                verify_data = self.redis.get(f"session:{session_id}")
                if verify_data:
                    logger.info("Session created and verified", session_id=session_id)
                else:
                    logger.error("Failed to verify session creation", session_id=session_id)
            finally:
                # Release the lock
                self.redis.delete(lock_key)
                
        except RedisError as e:
            logger.error("Redis error while creating session", error=str(e), session_id=session_id)
            raise
        except Exception as e:
            logger.error("Unexpected error while creating session", error=str(e), session_id=session_id)
            raise

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get session data if it exists and is not expired"""
        try:
            # Acquire Redis lock for session operations
            lock_key = f"lock:session:{session_id}"
            if not self.redis.set(lock_key, "1", ex=5, nx=True):
                logger.warning("Could not acquire lock for session", session_id=session_id)
                return None

            try:
                logger.debug("Retrieving session data", session_id=session_id)
                session_data = self.redis.get(f"session:{session_id}")
                
                if not session_data:
                    logger.warning("Session not found", session_id=session_id)
                    return None

                session = self._deserialize_session(session_data)
                last_activity = datetime.fromisoformat(session['last_activity'])
                
                if datetime.utcnow() - last_activity > timedelta(hours=24):
                    logger.warning("Session expired", session_id=session_id)
                    self.delete_session(session_id)
                    return None

                # Update last activity
                session['last_activity'] = datetime.utcnow().isoformat()
                updated_data = self._serialize_session(session)
                
                # Use pipeline for atomic operations
                with self.redis.pipeline() as pipe:
                    pipe.set(
                        f"session:{session_id}",
                        updated_data,
                        ex=86400  # 24 hours
                    )
                    pipe.set(
                        f"conversation:{session_id}",
                        self.redis.get(f"conversation:{session_id}"),
                        ex=86400  # 24 hours
                    )
                    pipe.execute()
                
                logger.debug("Session retrieved and updated", session_id=session_id)
                return session['user_data']
            finally:
                # Release the lock
                self.redis.delete(lock_key)
        except RedisError as e:
            logger.error("Redis error while getting session", error=str(e), session_id=session_id)
            return None
        except Exception as e:
            logger.error("Unexpected error while getting session", error=str(e), session_id=session_id)
            return None

    def delete_session(self, session_id: str) -> None:
        """Delete a session and its conversation history"""
        try:
            # Acquire Redis lock for session operations
            lock_key = f"lock:session:{session_id}"
            if not self.redis.set(lock_key, "1", ex=5, nx=True):
                logger.warning("Could not acquire lock for session", session_id=session_id)
                return

            try:
                logger.info("Deleting session", session_id=session_id)
                # Use pipeline for atomic operations
                with self.redis.pipeline() as pipe:
                    pipe.delete(f"session:{session_id}")
                    pipe.delete(f"conversation:{session_id}")
                    pipe.delete(lock_key)  # Also delete the lock
                    pipe.execute()
                logger.info("Session deleted successfully", session_id=session_id)
            finally:
                # Release the lock
                self.redis.delete(lock_key)
        except RedisError as e:
            logger.error("Failed to delete session", error=str(e), session_id=session_id)
            raise

    def add_to_conversation_history(self, session_id: str, message: dict) -> None:
        """Add a message to the conversation history of a session"""
        try:
            history_data = self.redis.get(f"conversation:{session_id}")
            history = json.loads(history_data) if history_data else []
            history.append(message)
            self.redis.set(
                f"conversation:{session_id}",
                json.dumps(history),
                ex=86400  # 24 hours
            )
            logger.debug("Message added to conversation history", session_id=session_id)
        except RedisError as e:
            logger.error("Failed to add to conversation history", error=str(e), session_id=session_id)
            raise

    def get_conversation_history(self, session_id: str) -> List[dict]:
        """Get the conversation history for a session"""
        try:
            history_data = self.redis.get(f"conversation:{session_id}")
            logger.debug("Retrieved conversation history", session_id=session_id)
            return json.loads(history_data) if history_data else []
        except RedisError as e:
            logger.error("Failed to get conversation history", error=str(e), session_id=session_id)
            return []

    def clear_conversation_history(self, session_id: str) -> None:
        """Clear the conversation history for a session without deleting the session"""
        try:
            # Acquire Redis lock for session operations
            lock_key = f"lock:session:{session_id}"
            if not self.redis.set(lock_key, "1", ex=5, nx=True):
                logger.warning("Could not acquire lock for session", session_id=session_id)
                return

            try:
                # Get current session data to preserve user data
                session_data = self.redis.get(f"session:{session_id}")
                if not session_data:
                    logger.error("Session not found while clearing history", session_id=session_id)
                    return

                session = self._deserialize_session(session_data)
                logger.info("Clearing conversation history", session_id=session_id)
                
                # Use pipeline for atomic operations
                with self.redis.pipeline() as pipe:
                    # Delete conversation history
                    pipe.delete(f"conversation:{session_id}")
                    # Update session with empty conversation history
                    pipe.set(
                        f"conversation:{session_id}",
                        json.dumps([]),
                        ex=86400  # 24 hours
                    )
                    # Update session last activity
                    session['last_activity'] = datetime.utcnow().isoformat()
                    pipe.set(
                        f"session:{session_id}",
                        self._serialize_session(session),
                        ex=86400  # 24 hours
                    )
                    pipe.execute()
                
                logger.info("Conversation history cleared successfully", session_id=session_id)
            finally:
                # Release the lock
                self.redis.delete(lock_key)
        except RedisError as e:
            logger.error("Failed to clear conversation history", error=str(e), session_id=session_id)
            raise 