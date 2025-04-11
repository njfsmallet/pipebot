import React, { KeyboardEvent, ChangeEvent, ClipboardEvent } from 'react';

interface CommandInputProps {
  input: string;
  isLoading: boolean;
  onInputChange: (e: ChangeEvent<HTMLTextAreaElement>) => void;
  onKeyDown: (e: KeyboardEvent<HTMLTextAreaElement>) => void;
  onPaste: (e: ClipboardEvent<HTMLTextAreaElement>) => void;
}

export const CommandInput: React.FC<CommandInputProps> = ({
  input,
  isLoading,
  onInputChange,
  onKeyDown,
  onPaste
}) => {
  if (isLoading) {
    return (
      <div className="prompt">
        <div className="loading-indicator">
        </div>
      </div>
    );
  }

  return (
    <div className="prompt">
      <span>&gt;_</span>
      <textarea
        className="input-line"
        value={input}
        onChange={onInputChange}
        onKeyDown={onKeyDown}
        onPaste={onPaste}
        rows={1}
        autoFocus
      />
    </div>
  );
}; 