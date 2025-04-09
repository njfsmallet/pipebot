import React from 'react';

interface LoginScreenProps {
  error: string | null;
  onLogin: () => void;
}

export const LoginScreen: React.FC<LoginScreenProps> = ({ error, onLogin }) => {
  return (
    <div className="login-container">
      <h1>PipeBot</h1>
      <p>Please sign in to continue</p>
      {error && <div className="error-message">{error}</div>}
      <button onClick={onLogin} className="login-button">
        Sign in with Microsoft
      </button>
    </div>
  );
}; 