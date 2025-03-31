from threading import Lock
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import logging
import json
import redis
from redis.exceptions import RedisError
from redis.connection import ConnectionPool
import os
import fcntl
import atexit
import time

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Set logger level to CRITICAL

class SessionManager:
    _instance = None
    _lock = Lock()
    _pool = None
    _redis = None
    _lock_file = "/tmp/pipebot_redis.lock"
    _config_file = "/tmp/pipebot_redis.json"
    _initialization_timeout = 10  # seconds

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SessionManager, cls).__new__(cls)
            return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self._lock_fd = None
            try:
                # Create lock file if it doesn't exist
                if not os.path.exists(self._lock_file):
                    with open(self._lock_file, 'w') as f:
                        f.write('')
                
                # Check if Redis is already initialized
                if os.path.exists(self._config_file):
                    logger.info("Redis configuration file exists, loading existing config")
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
                            logger.info("Timeout waiting for Redis initialization, loading existing config")
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
                if SessionManager._pool is None:
                    logger.info("Initializing new Redis connection pool")
                    SessionManager._pool = ConnectionPool(
                        host='localhost',
                        port=6379,
                        db=0,
                        decode_responses=True,
                        socket_timeout=5,
                        max_connections=20
                    )
                    # Test the pool with a temporary connection
                    test_client = redis.Redis(connection_pool=SessionManager._pool)
                    test_client.ping()
                    test_client.close()
                    logger.info("Successfully initialized Redis connection pool")

                    # Save the pool configuration
                    self._save_redis_config()
                else:
                    logger.info("Reusing existing Redis connection pool")
                
                # Use global Redis client if available
                if SessionManager._redis is None:
                    SessionManager._redis = redis.Redis(
                        connection_pool=SessionManager._pool,
                        socket_timeout=5,
                        retry_on_timeout=True
                    )
                    logger.info("Created new global Redis client")
                else:
                    logger.info("Reusing existing global Redis client")
                
                self.redis = SessionManager._redis
                self.initialized = True

                # Register cleanup
                atexit.register(self._cleanup)
                
            except RedisError as e:
                logger.error(f"Failed to connect to Redis: {e}")
                raise
            finally:
                if self._lock_fd:
                    try:
                        fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_UN)
                        self._lock_fd.close()
                    except Exception:
                        pass

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
        logger.info("Saved Redis configuration to file")

    def _load_redis_config(self):
        """Load Redis configuration from file"""
        try:
            with open(self._config_file, 'r') as f:
                config = json.load(f)
                SessionManager._pool = ConnectionPool(**config['pool'])
                SessionManager._redis = redis.Redis(
                    connection_pool=SessionManager._pool,
                    socket_timeout=5,
                    retry_on_timeout=True
                )
                self.redis = SessionManager._redis
                self.initialized = True
                logger.info("Loaded Redis configuration from file")
        except Exception as e:
            logger.error(f"Failed to load Redis configuration: {e}")
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
                logger.warning(f"Could not acquire lock for session {session_id}")
                return

            try:
                session_data = {
                    'user_data': user_data,
                    'created_at': datetime.utcnow().isoformat(),
                    'last_activity': datetime.utcnow().isoformat()
                }
                serialized_data = self._serialize_session(session_data)
                logger.info(f"Creating new session with ID: {session_id}")
                logger.debug(f"Session data to be saved: {serialized_data}")
                
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
                    logger.info(f"Session successfully created and verified in Redis: {session_id}")
                    logger.debug(f"Verified session data: {verify_data}")
                else:
                    logger.error(f"Failed to verify session creation: {session_id}")
            finally:
                # Release the lock
                self.redis.delete(lock_key)
                
        except RedisError as e:
            logger.error(f"Redis error while creating session: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error while creating session: {e}")
            raise

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get session data if it exists and is not expired"""
        try:
            # Acquire Redis lock for session operations
            lock_key = f"lock:session:{session_id}"
            if not self.redis.set(lock_key, "1", ex=5, nx=True):
                logger.warning(f"Could not acquire lock for session {session_id}")
                return None

            try:
                logger.info(f"Attempting to get session data for ID: {session_id}")
                session_data = self.redis.get(f"session:{session_id}")
                
                if not session_data:
                    logger.warning(f"Session not found in Redis: {session_id}")
                    return None

                logger.debug(f"Raw session data from Redis: {session_data}")
                session = self._deserialize_session(session_data)
                last_activity = datetime.fromisoformat(session['last_activity'])
                
                if datetime.utcnow() - last_activity > timedelta(hours=24):
                    logger.warning(f"Session expired: {session_id}")
                    self.delete_session(session_id)
                    return None

                # Update last activity
                session['last_activity'] = datetime.utcnow().isoformat()
                updated_data = self._serialize_session(session)
                logger.debug(f"Updating session with data: {updated_data}")
                
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
                
                logger.info(f"Session accessed and updated successfully: {session_id}")
                return session['user_data']
            finally:
                # Release the lock
                self.redis.delete(lock_key)
        except RedisError as e:
            logger.error(f"Redis error while getting session: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error while getting session: {e}")
            return None

    def update_session(self, session_id: str, user_data: dict) -> None:
        """Update session data"""
        try:
            session_data = self.redis.get(f"session:{session_id}")
            if not session_data:
                return

            session = self._deserialize_session(session_data)
            session['user_data'] = user_data
            session['last_activity'] = datetime.utcnow().isoformat()
            
            self.redis.set(
                f"session:{session_id}",
                self._serialize_session(session),
                ex=86400  # 24 hours
            )
        except RedisError as e:
            logger.error(f"Failed to update session: {e}")
            raise

    def delete_session(self, session_id: str) -> None:
        """Delete a session and its conversation history"""
        try:
            # Acquire Redis lock for session operations
            lock_key = f"lock:session:{session_id}"
            if not self.redis.set(lock_key, "1", ex=5, nx=True):
                logger.warning(f"Could not acquire lock for session {session_id}")
                return

            try:
                logger.info(f"Deleting session: {session_id}")
                # Use pipeline for atomic operations
                with self.redis.pipeline() as pipe:
                    pipe.delete(f"session:{session_id}")
                    pipe.delete(f"conversation:{session_id}")
                    pipe.delete(lock_key)  # Also delete the lock
                    pipe.execute()
                logger.info(f"Session successfully deleted: {session_id}")
            finally:
                # Release the lock
                self.redis.delete(lock_key)
        except RedisError as e:
            logger.error(f"Failed to delete session: {e}")
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
        except RedisError as e:
            logger.error(f"Failed to add to conversation history: {e}")
            raise

    def get_conversation_history(self, session_id: str) -> List[dict]:
        """Get the conversation history for a session"""
        try:
            history_data = self.redis.get(f"conversation:{session_id}")
            return json.loads(history_data) if history_data else []
        except RedisError as e:
            logger.error(f"Failed to get conversation history: {e}")
            return []

    def _is_session_expired(self, session: dict) -> bool:
        """Check if a session has expired (24 hours)"""
        last_activity = session['last_activity']
        return datetime.utcnow() - last_activity > timedelta(hours=24)

    def cleanup_expired_sessions(self) -> None:
        """Remove all expired sessions"""
        with self._lock:
            expired_sessions = [
                session_id for session_id, session in self.sessions.items()
                if self._is_session_expired(session)
            ]
            for session_id in expired_sessions:
                self.delete_session(session_id)

    def clear_conversation_history(self, session_id: str) -> None:
        """Clear the conversation history for a session without deleting the session"""
        try:
            # Acquire Redis lock for session operations
            lock_key = f"lock:session:{session_id}"
            if not self.redis.set(lock_key, "1", ex=5, nx=True):
                logger.warning(f"Could not acquire lock for session {session_id}")
                return

            try:
                # Get current session data to preserve user data
                session_data = self.redis.get(f"session:{session_id}")
                if not session_data:
                    logger.error(f"Session not found while clearing history: {session_id}")
                    return

                session = self._deserialize_session(session_data)
                logger.info(f"Clearing conversation history for session: {session_id}")
                
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
                
                logger.info(f"Conversation history successfully cleared for session: {session_id}")
            finally:
                # Release the lock
                self.redis.delete(lock_key)
        except RedisError as e:
            logger.error(f"Failed to clear conversation history: {e}")
            raise 