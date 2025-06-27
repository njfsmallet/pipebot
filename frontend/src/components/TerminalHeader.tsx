import React from 'react';
import { User } from '../types';

interface TerminalHeaderProps {
  user: User | null;
  onLogout: () => void;
}

export const TerminalHeader: React.FC<TerminalHeaderProps> = ({
  user,
  onLogout
}) => {
  return (
    <div className="terminal-header">
      <div></div>
      <div className="user-info">
        {user && (
          <>
            <span>{user.name}</span>
            <button onClick={onLogout} className="logout-button" title="Sign out">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                <polyline points="16 17 21 12 16 7"></polyline>
                <line x1="21" y1="12" x2="9" y2="12"></line>
              </svg>
            </button>
          </>
        )}
      </div>
    </div>
  );
}; 