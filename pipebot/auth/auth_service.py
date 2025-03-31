from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
import jwt
from typing import Optional, Dict, Any
from .azure_config import AzureConfig
from azure.identity import ClientSecretCredential
from azure.core.exceptions import ClientAuthenticationError
import requests

class AuthService:
    def __init__(self, config: AzureConfig):
        self.config = config
        self.credential = config.credential

    def get_login_url(self) -> str:
        """Generate the Azure Entra ID login URL."""
        url = f"{self.config.authority}/oauth2/v2.0/authorize?" + \
               f"client_id={self.config.client_id}&" + \
               f"response_type=code&" + \
               f"redirect_uri={self.config.redirect_uri}&" + \
               f"scope={' '.join(self.config.scopes)}"
        return url

    async def handle_callback(self, request: Request) -> Dict[str, Any]:
        """Handle the OAuth callback from Azure Entra ID."""
        code = request.query_params.get("code")
        if not code:
            raise HTTPException(status_code=400, detail="No authorization code received")

        try:
            # Exchange the authorization code for tokens
            token_endpoint = f"{self.config.authority}/oauth2/v2.0/token"
            token_data = {
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": self.config.redirect_uri
            }
            
            response = requests.post(token_endpoint, data=token_data)
            
            if not response.ok:
                print("Token exchange failed:", response.text)
                raise HTTPException(status_code=400, detail=f"Token exchange failed: {response.text}")
                
            token_response = response.json()
            
            access_token = token_response.get("access_token")
            id_token = token_response.get("id_token")
            
            if not access_token or not id_token:
                raise HTTPException(status_code=400, detail="Invalid token response")
            
            # Get user info from the ID token
            user_info = self._decode_id_token(id_token)
            
            # Check if user's email is allowed
            email = user_info.get("email")
            if not email or not self.config.is_email_allowed(email):
                print(f"Access denied for email: {email}")
                raise HTTPException(
                    status_code=403,
                    detail="Your email is not authorized to access this application"
                )
            
            return {
                "access_token": access_token,
                "id_token": id_token,
                "user_info": user_info
            }
        except ClientAuthenticationError as e:
            print("Client authentication error:", str(e))
            raise HTTPException(status_code=401, detail=str(e))
        except Exception as e:
            print("Authentication error:", str(e))
            raise HTTPException(status_code=400, detail=str(e))

    def _decode_id_token(self, token: str) -> Dict[str, Any]:
        """Decode and verify the token."""
        try:
            decoded = jwt.decode(
                token,
                options={"verify_signature": False}
            )
            
            # Get the full name and split it into parts
            full_name = decoded.get("name", "")
            name_parts = full_name.split()
            
            if len(name_parts) >= 2:
                # Find the part that is in uppercase (the last name)
                last_name = next((part for part in name_parts if part.isupper()), name_parts[-1])
                # Get all other parts as first name
                first_name_parts = [part for part in name_parts if part != last_name]
                first_name = " ".join(first_name_parts)
                # Combine in the new order: FirstName LASTNAME
                formatted_name = f"{first_name} {last_name}"
            else:
                # If we can't split the name, just use it as is
                formatted_name = full_name
            
            # Try different possible email fields
            email = decoded.get("upn") or decoded.get("email") or decoded.get("preferred_username")
            
            user_info = {
                "sub": decoded.get("sub"),
                "name": formatted_name,
                "email": email,
                "roles": decoded.get("roles", [])
            }
            return user_info
        except Exception as e:
            print("Error decoding token:", str(e))
            raise HTTPException(status_code=400, detail=f"Invalid token: {str(e)}")

    def get_logout_url(self) -> str:
        """Generate the Azure Entra ID logout URL."""
        post_logout_redirect_uri = self.config.redirect_uri.rsplit('/', 1)[0]  # Remove '/callback' from the redirect URI
        url = f"{self.config.authority}/oauth2/v2.0/logout?" + \
              f"post_logout_redirect_uri={post_logout_redirect_uri}"
        return url 