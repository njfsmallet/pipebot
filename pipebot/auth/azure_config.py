from dataclasses import dataclass, field
from azure.identity import ClientSecretCredential

@dataclass(frozen=True)
class AzureConfig:
    tenant_id: str = 'fxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx5'
    client_id: str = '1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx9'
    client_secret: str = 'Axxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxm'
    client_secret_id: str = '8xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxc'
    redirect_uri: str = 'https://pipebot.example.com/oauth/openid/callback'
    authority: str = 'https://login.microsoftonline.com/fxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx5'
    scopes: list = field(default_factory=lambda: ['openid', 'profile', 'email'])
    session_secret: str = 'secret123'
    dev_mode: bool = False
    allowed_emails: list = field(default_factory=lambda: [
        'user1@example.com',
        'user2@example.com',
        'user3@example.com'
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
