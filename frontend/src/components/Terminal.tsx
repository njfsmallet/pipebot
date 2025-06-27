import React, { useRef, useEffect } from 'react';
import { TerminalHeader } from './TerminalHeader';
import { TerminalContent } from './TerminalContent';
import { CommandInput } from './CommandInput';
import { User, HistoryItem } from '../types';

interface TerminalProps {
  user: User | null;
  history: HistoryItem[];
  input: string;
  isLoading: boolean;
  error: string | null;
  hiddenOutputs: Set<number | string>;
  onLogout: () => void;
  onToggleOutput: (index: number | string) => void;
  onInputChange: React.ChangeEventHandler<HTMLTextAreaElement>;
  onKeyDown: React.KeyboardEventHandler<HTMLTextAreaElement>;
  onPaste: React.ClipboardEventHandler<HTMLTextAreaElement>;
}

export const Terminal: React.FC<TerminalProps> = ({
  user,
  history,
  input,
  isLoading,
  error,
  hiddenOutputs,
  onLogout,
  onToggleOutput,
  onInputChange,
  onKeyDown,
  onPaste
}) => {
  const terminalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [history]);

  return (
    <div className="terminal">
      <TerminalHeader
        user={user}
        onLogout={onLogout}
      />
      
      <TerminalContent
        ref={terminalRef}
        history={history}
        hiddenOutputs={hiddenOutputs}
        onToggleOutput={onToggleOutput}
        error={error}
      />
      
      <CommandInput
        input={input}
        isLoading={isLoading}
        onInputChange={onInputChange}
        onKeyDown={onKeyDown}
        onPaste={onPaste}
      />
    </div>
  );
}; 