import logging
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import sys
import os
import base64
import uuid
from typing import Optional, Dict, Any
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Add Pipebot path to PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipebot.auth.azure_config import AzureConfig
from pipebot.auth.auth_service import AuthService
from pipebot.interface import PipebotInterface
from session_manager import SessionManager

app = FastAPI()

# CORS configuration to allow requests from frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://pipebot.example.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Mount the frontend static files
frontend_path = "/var/www/pipebot/dist"
app.mount("/static", StaticFiles(directory=frontend_path), name="static")

# Initialize Azure Entra ID configuration and session manager
azure_config = AzureConfig(dev_mode=False)
auth_service = AuthService(azure_config)
session_manager = SessionManager()

# Dependency to get current user
async def get_current_user(request: Request):
    if azure_config.dev_mode:
        return {
            "email": "dev.user@example.com",
            "name": "Development User",
            "preferred_username": "dev.user@example.com"
        }
        
    session_id = request.cookies.get("session_id")
    logger.debug(f"Cookies in request: {request.cookies}")
    logger.debug(f"Request headers: {request.headers}")
  
    if not session_id:
        logger.error("No session_id found in cookies")
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    logger.debug(f"Found session_id in cookies: {session_id}")
    user_data = session_manager.get_session(session_id)
    if not user_data:
        logger.error(f"No user data found for session_id: {session_id}")
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    logger.debug(f"Successfully retrieved user data for session_id: {session_id}")
    return user_data

@app.get("/")
async def read_root():
    return FileResponse(os.path.join(frontend_path, "index.html"))

@app.get("/api/auth/login")
async def login():
    """Redirect to Azure Entra ID login page or handle dev mode."""
    if azure_config.dev_mode:
        # In development mode, create a session and redirect to home
        session_id = str(uuid.uuid4())
        user_data = {
            "email": "dev.user@example.com",
            "name": "Development User",
            "preferred_username": "dev.user@example.com"
        }
        session_manager.create_session(session_id, user_data)
        
        response = RedirectResponse(url="https://pipebot.example.com/")
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
            domain="pipebot.example.com",
            max_age=86400
        )
        return response
        
    login_url = auth_service.get_login_url()
    return RedirectResponse(login_url)

@app.get("/oauth/openid/callback")
async def callback(request: Request):
    """Handle Azure Entra ID callback."""
    try:
        result = await auth_service.handle_callback(request)
        if not result or "access_token" not in result:
            logger.error("Failed to get access token")
            raise HTTPException(status_code=400, detail="Failed to get access token")
            
        logger.info("Authentication successful for user: %s", result.get("user_info", {}).get("email"))
        
        # Create a new session
        session_id = str(uuid.uuid4())
        session_manager.create_session(session_id, result["user_info"])
        
        # Create response with absolute URL
        response = RedirectResponse(
            url="https://pipebot.example.com/",
            status_code=302
        )
        
        # First delete any existing session cookie
        response.delete_cookie(
            key="session_id",
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
            domain="pipebot.example.com"
        )
        
        # Then set the new cookie
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
            domain="pipebot.example.com",
            max_age=86400
        )
        
        logger.debug(f"Setting new cookie session_id={session_id} in callback response")
        return response
    except HTTPException as e:
        logger.error("Authentication error: %s", str(e.detail))
        return RedirectResponse(url=f"/?error={str(e.detail)}")
    except Exception as e:
        logger.error("Authentication failed: %s", str(e))
        return RedirectResponse(url=f"/?error=Authentication failed: {str(e)}")

@app.get("/api/auth/logout")
async def logout(request: Request):
    """Handle logout by removing the session."""
    session_id = request.cookies.get("session_id")
    if session_id:
        session_manager.delete_session(session_id)
    
    response = RedirectResponse(url="https://pipebot.example.com/")
    response.delete_cookie(
        key="session_id",
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
        domain="pipebot.example.com"
    )
    return response

@app.get("/api/auth/user")
async def get_user(request: Request):
    """Get current user information."""
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
    command: str = ""
    image: Optional[str] = None
    imageType: Optional[str] = None
    smartMode: Optional[bool] = False

@app.post("/api/converse")
async def converse(cmd: Command, request: Request, current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Process a conversation command with optional image input.
    
    Args:
        cmd (Command): The command object containing the text command and optional image data
        request (Request): The FastAPI request object
        current_user (Dict[str, Any]): The current user's data
        
    Returns:
        dict: Response containing the output text
    """
    try:
        session_id = request.cookies.get("session_id")
        pipebot = PipebotInterface.get_instance()
        
        if cmd.image:
            # Convert base64 to raw bytes for Bedrock API
            image_bytes = base64.b64decode(cmd.image)
            response = await pipebot.process_input(
                cmd.command, 
                image_bytes, 
                cmd.imageType,
                session_id,
                smart_mode=cmd.smartMode
            )
        else:
            response = await pipebot.process_input(
                cmd.command,
                session_id=session_id,
                smart_mode=cmd.smartMode
            )
            
        if response:
            return {"output": response.strip()}
        return {"output": ""}
        
    except Exception as e:
        logger.error("Error processing request: %s", e)
        return {"error": str(e)}, 500

@app.post("/api/clear")
async def clear(request: Request, current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Clear the conversation history for the current user.
    """
    try:
        if azure_config.dev_mode:
            # In dev mode, we can use a fixed session ID
            session_id = "dev_session"
            session_manager.clear_conversation_history(session_id)
            return {"status": "success", "message": "Conversation history cleared"}
            
        session_id = request.cookies.get("session_id")
        if not session_id:
            raise HTTPException(status_code=401, detail="Not authenticated")
            
        # Get current user data to verify session
        user_data = session_manager.get_session(session_id)
        if not user_data:
            raise HTTPException(status_code=401, detail="Not authenticated")
            
        # Clear conversation history while preserving user data
        session_manager.clear_conversation_history(session_id)
        
        return {"status": "success", "message": "Conversation history cleared"}
        
    except Exception as e:
        logger.error("Error clearing conversation: %s", e)
        return {"error": str(e)}, 500

@app.get("/api/conversation/history")
async def get_conversation_history(request: Request, current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Get the conversation history for the current user.
    
    Returns:
        list: List of conversation messages
    """
    try:
        session_id = request.cookies.get("session_id")
        history = session_manager.get_conversation_history(session_id)
        return {"history": history}
    except Exception as e:
        logger.error("Error getting conversation history: %s", e)
        return {"error": str(e)}, 500

# Global Pipebot instance
pipebot_instance = None

# Application initialization
@app.on_event("startup")
async def startup_event():
    """
    Initialize the application and create the Pipebot instance.
    """
    global pipebot_instance
    pipebot_instance = PipebotInterface.get_instance()

@app.on_event("shutdown")
async def shutdown_event():
    """
    Clean up resources when the application shuts down.
    """
    global pipebot_instance
    pipebot_instance = None 
