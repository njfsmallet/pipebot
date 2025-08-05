from dataclasses import dataclass, field
from azure.identity import ClientSecretCredential

@dataclass(frozen=True)
class AzureConfig:
    # Azure AD Configuration - Replace with your own values
    tenant_id: str = 'your-tenant-id-here'
    client_id: str = 'your-client-id-here'
    client_secret: str = 'your-client-secret-here'
    client_secret_id: str = 'your-client-secret-id-here'
    redirect_uri: str = 'https://your-domain.com/oauth/openid/callback'
    authority: str = 'https://login.microsoftonline.com/your-tenant-id-here'
    scopes: list = field(default_factory=lambda: ['openid', 'profile', 'email'])
    session_secret: str = 'your-session-secret-here'
    dev_mode: bool = False
    allowed_emails: list = field(default_factory=lambda: [
        # Add your allowed email addresses here
        'admin@your-domain.com',
        'user1@your-domain.com',
        'user2@your-domain.com'
    ])

    @property
    def credential(self):
        if self.dev_mode:
            return None
        return ClientSecretCredential(
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            client_secret=self.client_secret
        )
        
    @property
    def client_credential(self):
        """Returns the client secret for MSAL authentication"""
        if self.dev_mode:
            return None
        return self.client_secret

    def is_email_allowed(self, email: str) -> bool:
        """Check if the given email is in the list of allowed emails."""
        if self.dev_mode:
            return True  # In dev mode, all emails are allowed
        return email in self.allowed_emails 
