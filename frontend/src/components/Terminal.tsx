import React, { useRef, useEffect } from 'react';
import { TerminalHeader } from './TerminalHeader';
import { TerminalContent } from './TerminalContent';
import { CommandInput } from './CommandInput';
import { User, HistoryItem, SmartModeState } from '../types';

interface TerminalProps {
  user: User | null;
  smartMode: SmartModeState;
  history: HistoryItem[];
  input: string;
  isLoading: boolean;
  error: string | null;
  hiddenOutputs: Set<number | string>;
  onToggleSmartMode: () => void;
  onLogout: () => void;
  onToggleOutput: (index: number | string) => void;
  onInputChange: React.ChangeEventHandler<HTMLTextAreaElement>;
  onKeyDown: React.KeyboardEventHandler<HTMLTextAreaElement>;
  onPaste: React.ClipboardEventHandler<HTMLTextAreaElement>;
}

export const Terminal: React.FC<TerminalProps> = ({
  user,
  smartMode,
  history,
  input,
  isLoading,
  error,
  hiddenOutputs,
  onToggleSmartMode,
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
        smartMode={smartMode}
        onToggleSmartMode={onToggleSmartMode}
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