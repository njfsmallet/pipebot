import logging
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import sys
import os
import base64
import uuid
import json
import asyncio
from typing import Optional, Dict, Any, AsyncGenerator
from datetime import datetime
from starlette.middleware.base import BaseHTTPMiddleware

# Configuration du logging
from logging_config import StructuredLogger, setup_logging, correlation_id
setup_logging()
logger = StructuredLogger(__name__)

class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Middleware to handle correlation ID for each request."""
    
    async def dispatch(self, request: Request, call_next):
        # Generate a new correlation ID for each request
        request_id = str(uuid.uuid4())
        correlation_id.set(request_id)
        
        # Process the request
        response = await call_next(request)
        
        # Add correlation ID to response headers
        response.headers["X-Correlation-ID"] = request_id
        
        return response

# Import configuration
from config import config

# Add Pipebot path to PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipebot.auth.azure_config import AzureConfig
from pipebot.auth.auth_service import AuthService
from pipebot.interface import PipebotInterface
from session_manager import SessionManager
from pipebot.config import AppConfig

app = FastAPI(
    title="Pipebot API",
    description="API for Pipebot conversation service",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# Add correlation ID middleware
app.add_middleware(CorrelationIDMiddleware)

# CORS configuration to allow requests from frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Mount the frontend static files
app.mount("/static", StaticFiles(directory=config.FRONTEND_PATH), name="static")

# Initialize Azure Entra ID configuration
azure_config = AzureConfig(dev_mode=False)
auth_service = AuthService(azure_config)

# Dependency to get SessionManager instance
def get_session_manager() -> SessionManager:
    """Get a SessionManager instance.
    
    Returns:
        SessionManager: A new instance of SessionManager
    """
    return SessionManager()

# Dependency to get current user
async def get_current_user(
    request: Request,
    session_manager: SessionManager = Depends(get_session_manager)
):
    if azure_config.dev_mode:
        return {
            "email": "dev.user@example.com",
            "name": "Development User",
            "preferred_username": "dev.user@example.com"
        }
        
    session_id = request.cookies.get("session_id")
    logger.debug("Request cookies", cookies=request.cookies)
    logger.debug("Request headers", headers=dict(request.headers))
  
    if not session_id:
        logger.error("Authentication failed: no session_id found in cookies")
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    logger.debug("Session found", session_id=session_id)
    user_data = session_manager.get_session(session_id)
    if not user_data:
        logger.error("Authentication failed: no user data found", session_id=session_id)
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    logger.debug("User data retrieved successfully", session_id=session_id)
    return user_data

@app.get("/")
async def read_root():
    """
    Serve the main frontend application.
    
    Returns:
        FileResponse: The index.html file from the frontend directory
    """
    return FileResponse(os.path.join(config.FRONTEND_PATH, "index.html"))

@app.get("/health", status_code=200)
async def health_check():
    """
    Health check endpoint for monitoring the API's status.
    
    Returns:
        dict: A JSON response containing:
            - status (str): Always "healthy"
            - timestamp (str): Current ISO format timestamp
    """
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/api/auth/login")
async def login(session_manager: SessionManager = Depends(get_session_manager)):
    """
    Initiate the authentication process.
    
    In development mode, creates a mock session and redirects to home.
    In production, redirects to Azure Entra ID login page.
    
    Returns:
        RedirectResponse: Redirects to either:
            - Home page (in dev mode)
            - Azure Entra ID login page (in production)
    """
    if azure_config.dev_mode:
        # In development mode, create a session and redirect to home
        session_id = str(uuid.uuid4())
        user_data = {
            "email": "dev.user@example.com",
            "name": "Development User",
            "preferred_username": "dev.user@example.com"
        }
        session_manager.create_session(session_id, user_data)
        
        response = RedirectResponse(url=f"{config.BASE_URL}/")
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
            domain=config.COOKIE_DOMAIN,
            max_age=config.SESSION_MAX_AGE
        )
        return response
        
    login_url = auth_service.get_login_url()
    return RedirectResponse(login_url)

@app.get("/oauth/openid/callback")
async def callback(
    request: Request,
    session_manager: SessionManager = Depends(get_session_manager)
):
    """
    Handle the OAuth callback from Azure Entra ID.
    
    Processes the authentication response, creates a new session,
    and sets the session cookie.
    
    Args:
        request (Request): The FastAPI request object containing OAuth callback data
        
    Returns:
        RedirectResponse: Redirects to:
            - Home page on success
            - Error page with error message on failure
            
    Raises:
        HTTPException: If authentication fails or access token is missing
    """
    try:
        result = await auth_service.handle_callback(request)
        if not result or "access_token" not in result:
            logger.error("Failed to get access token")
            raise HTTPException(status_code=400, detail="Failed to get access token")
            
        logger.info("Authentication successful", user_email=result.get("user_info", {}).get("email"))
        
        # Create a new session
        session_id = str(uuid.uuid4())
        session_manager.create_session(session_id, result["user_info"])
        
        # Create response with absolute URL
        response = RedirectResponse(
            url=f"{config.BASE_URL}/",
            status_code=302
        )
        
        # First delete any existing session cookie
        response.delete_cookie(
            key="session_id",
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
            domain=config.COOKIE_DOMAIN
        )
        
        # Then set the new cookie
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
            domain=config.COOKIE_DOMAIN,
            max_age=config.SESSION_MAX_AGE
        )
        
        logger.debug(f"Setting new cookie session_id={session_id} in callback response")
        return response
    except HTTPException as e:
        logger.error("Authentication error", error=str(e.detail))
        return RedirectResponse(url=f"/?error={str(e.detail)}")
    except Exception as e:
        logger.error("Authentication failed", error=str(e))
        return RedirectResponse(url=f"/?error=Authentication failed: {str(e)}")

@app.get("/api/auth/logout")
async def logout(
    request: Request,
    session_manager: SessionManager = Depends(get_session_manager)
):
    """
    Handle user logout by removing the session and clearing cookies.
    
    Args:
        request (Request): The FastAPI request object
        
    Returns:
        RedirectResponse: Redirects to the home page
    """
    session_id = request.cookies.get("session_id")
    if session_id:
        session_manager.delete_session(session_id)
    
    response = RedirectResponse(url=f"{config.BASE_URL}/")
    response.delete_cookie(
        key="session_id",
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
        domain=config.COOKIE_DOMAIN
    )
    return response

@app.get("/api/auth/user")
async def get_user(
    request: Request,
    session_manager: SessionManager = Depends(get_session_manager)
):
    """
    Retrieve the current authenticated user's information.
    
    Args:
        request (Request): The FastAPI request object
        
    Returns:
        dict: User information containing:
            - email (str)
            - name (str)
            - preferred_username (str)
            
    Raises:
        HTTPException: If user is not authenticated (401)
    """
    if azure_config.dev_mode:
        return {
            "email": "dev.user@example.com",
            "name": "Development User",
            "preferred_username": "dev.user@example.com"
        }
        
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_data = session_manager.get_session(session_id)
    if not user_data:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return user_data

class Command(BaseModel):
    """
    Model representing a conversation command with optional image input.
    
    Attributes:
        command (str): The text command to process
        image (Optional[str]): Base64 encoded image data
        imageType (Optional[str]): MIME type of the image (e.g., 'image/jpeg', 'image/png')
    """
    command: str = ""
    image: Optional[str] = None
    imageType: Optional[str] = None

# Dependency to get PipebotInterface instance
def get_pipebot(session_manager: SessionManager = Depends(get_session_manager)) -> PipebotInterface:
    """Get a PipebotInterface instance.
    
    Args:
        session_manager: The SessionManager instance to use
        
    Returns:
        PipebotInterface: A new instance of PipebotInterface
    """
    return PipebotInterface(app_config=AppConfig(), session_manager=session_manager)

@app.post("/api/converse")
async def converse(
    cmd: Command,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    pipebot: PipebotInterface = Depends(get_pipebot)
):
    """
    Process a conversation command with optional image input.
    
    This endpoint handles both text-only and image-based conversations,
    processing them through the Pipebot interface.
    
    Args:
        cmd (Command): The command object containing:
            - command (str): Text command to process
            - image (Optional[str]): Base64 encoded image data
            - imageType (Optional[str]): MIME type of the image
        request (Request): The FastAPI request object
        current_user (Dict[str, Any]): The current authenticated user's data
        pipebot (PipebotInterface): The Pipebot interface instance
        
    Returns:
        dict: Response containing:
            - output (str): The processed response text
            
    Raises:
        HTTPException: If processing fails (500)
    """
    try:
        session_id = request.cookies.get("session_id")
        
        if cmd.image:
            # Convert base64 to raw bytes for Bedrock API
            image_bytes = base64.b64decode(cmd.image)
            response = await pipebot.process_input(
                cmd.command, 
                image_bytes, 
                cmd.imageType,
                session_id
            )
        else:
            response = await pipebot.process_input(
                cmd.command,
                session_id=session_id
            )
            
        if response:
            return {"output": response.strip()}
        return {"output": ""}
        
    except Exception as e:
        logger.error("Error processing request: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/converse/stream")
async def converse_stream(
    cmd: Command,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    pipebot: PipebotInterface = Depends(get_pipebot)
):
    """
    Process a conversation command with streaming intermediate updates.
    
    This endpoint handles both text-only and image-based conversations,
    processing them through the Pipebot interface and streaming tool execution updates.
    
    Args:
        cmd (Command): The command object containing:
            - command (str): Text command to process
            - image (Optional[str]): Base64 encoded image data
            - imageType (Optional[str]): MIME type of the image
        request (Request): The FastAPI request object
        current_user (Dict[str, Any]): The current authenticated user's data
        pipebot (PipebotInterface): The Pipebot interface instance
        
    Returns:
        StreamingResponse: Server-sent events stream of processing updates
    """
    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            session_id = request.cookies.get("session_id")
            
            # Initial status removed for cleaner output
            
            if cmd.image:
                # Convert base64 to raw bytes for Bedrock API
                image_bytes = base64.b64decode(cmd.image)
                async for update in pipebot.process_input_stream(
                    cmd.command, 
                    image_bytes, 
                    cmd.imageType,
                    session_id
                ):
                    yield f"data: {json.dumps(update)}\n\n"
            else:
                async for update in pipebot.process_input_stream(
                    cmd.command,
                    session_id=session_id
                ):
                    yield f"data: {json.dumps(update)}\n\n"
                    
        except Exception as e:
            logger.error("Error in streaming request", error=str(e), traceback=str(e.__traceback__))
            error_update = {'type': 'error', 'message': str(e)}
            yield f"data: {json.dumps(error_update)}\n\n"
        finally:
            pass
    
    return StreamingResponse(
        event_stream(), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )

@app.post("/api/clear")
async def clear(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    pipebot: PipebotInterface = Depends(get_pipebot),
    session_manager: SessionManager = Depends(get_session_manager)
):
    """
    Clear the conversation history for the current user.
    """
    try:
        if azure_config.dev_mode:
            # In dev mode, we can use a fixed session ID
            session_id = "dev_session"
            pipebot.clear_conversation_history(session_id)
            return {"status": "success", "message": "Conversation history cleared"}
            
        session_id = request.cookies.get("session_id")
        if not session_id:
            raise HTTPException(status_code=401, detail="Not authenticated")
            
        # Get current user data to verify session
        user_data = session_manager.get_session(session_id)
        if not user_data:
            raise HTTPException(status_code=401, detail="Not authenticated")
            
        # Clear conversation history while preserving user data
        pipebot.clear_conversation_history(session_id)
        
        return {"status": "success", "message": "Conversation history cleared"}
        
    except Exception as e:
        logger.error("Error clearing conversation: %s", e)
        return {"error": str(e)}, 500

@app.get("/api/conversation/history")
async def get_conversation_history(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    pipebot: PipebotInterface = Depends(get_pipebot)
):
    """
    Get the conversation history for the current user.
    
    Returns:
        list: List of conversation messages
    """
    try:
        session_id = request.cookies.get("session_id")
        if not session_id:
            raise HTTPException(status_code=401, detail="Not authenticated")
            
        history = pipebot.session_manager.get_conversation_history(session_id)
        return {"history": history}
    except Exception as e:
        logger.error("Error getting conversation history: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
