import React, { useRef, useEffect, useState, useCallback, memo } from 'react';
import { MarkdownRenderer } from './MarkdownRenderer';
import { User, HistoryItem } from '../types';
import PromptSpinner from './PromptSpinner';

interface TerminalProps {
  user: User | null;
  history: HistoryItem[];
  input: string;
  isLoading: boolean;
  error: string | null;
  onLogout: () => void;
  onInputChange: React.ChangeEventHandler<HTMLTextAreaElement>;
  onKeyDown: React.KeyboardEventHandler<HTMLTextAreaElement>;
  onPaste: React.ClipboardEventHandler<HTMLTextAreaElement>;
  onSubmit: () => void;
  onRetry?: (content: string) => void;
}

// Composant HistoryLine intégré
const HistoryLineComponent: React.FC<{
  item: HistoryItem;
  responseItems?: HistoryItem[];
  startUserInteraction?: () => void;
  onRetry?: (content: string) => void;
}> = ({
  item,
  responseItems = [],
  startUserInteraction,
  onRetry
}) => {
  const [isImageExpanded, setIsImageExpanded] = useState(false);
  const [isToolOutputExpanded, setIsToolOutputExpanded] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  const handleImageClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setIsImageExpanded(!isImageExpanded);
  }, [isImageExpanded]);

  const handleToolOutputToggle = useCallback(() => {
    setIsToolOutputExpanded(!isToolOutputExpanded);
  }, [isToolOutputExpanded]);

  const handleCopy = useCallback((text: string) => {
    navigator.clipboard.writeText(text);
  }, []);

  const handleRetry = useCallback(() => {
    if (onRetry && item.content) {
      // Use the content directly (no more ">_ " prefix)
      onRetry(item.content);
    }
  }, [onRetry, item.content]);

  // Image handling
  if (item.type === 'image') {
    return (
      <div className="history-line">
        <div 
          className={`image-container ${isImageExpanded ? 'expanded' : ''}`}
          onClick={handleImageClick}
        >
          <div className="image-header">
            <div className="image-preview">
              <img 
                src={item.imageData} 
                alt="Thumbnail" 
                className="image-thumbnail"
              />
              <span className="image-text">{item.content}</span>
            </div>
            <button className="toggle-button">
              {isImageExpanded ? '−' : '+'}
            </button>
          </div>
          {isImageExpanded && (
            <div className="image-full">
              <img 
                src={item.imageData} 
                alt="Full size" 
                className="full-image"
              />
            </div>
          )}
        </div>
        {responseItems.length > 0 && (
          <div className="agent-response">
            {responseItems.map((responseItem, i) => (
              <div key={`response-${i}`} className="response-item">
                <MarkdownRenderer content={responseItem.content} />
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // User commands (user-message type items are user messages)
  if (item.type === 'user-message') {
    return (
      <div className="history-line">
        <div
          className="command-line"
          onMouseEnter={() => setIsHovered(true)}
          onMouseLeave={() => setIsHovered(false)}
        >
          {item.content}
          {isHovered && (
            <div className="message-actions">
              <button
                className="action-button copy-action"
                onClick={() => handleCopy(item.content)}
                title="Copy message"
              >
                📋
              </button>
              <button
                className="action-button retry-action"
                onClick={handleRetry}
                title="Retry command"
              >
                🔄
              </button>
            </div>
          )}
        </div>
        {responseItems.length > 0 && (
          <div className="agent-response">
            {responseItems.map((responseItem, i) => (
              <div key={`response-${i}`} className="response-item">
                <MarkdownRenderer content={responseItem.content} />
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // Progress items (tool commands) - CLI style
  if (item.type === 'progress') {
    // Check if this is a system command (starts with $)
    if (item.content.startsWith('$')) {

      // Extract command name and content
      const contentAfterDollar = item.content.substring(1).trim(); // Remove leading space after $
      const firstSpaceIndex = contentAfterDollar.indexOf(' ');
      const commandName = firstSpaceIndex > 0 ? contentAfterDollar.substring(0, firstSpaceIndex) : contentAfterDollar;
      const commandContent = firstSpaceIndex > 0 ? contentAfterDollar.substring(firstSpaceIndex + 1) : '';
      
      // Try to parse as JSON for better formatting
      let formattedContent = commandContent;
      
      try {
        const jsonObj = JSON.parse(commandContent);
        formattedContent = JSON.stringify(jsonObj, null, 2);
      } catch {
        // Not JSON, use as-is
        formattedContent = commandContent;
      }
      
      // Get output content if available
      const outputContent = item.output !== undefined && item.output !== null 
        ? (typeof item.output === 'object' ? JSON.stringify(item.output, null, 2) : String(item.output))
        : '';
      
      const isLongOutput = formattedContent.length > 500;
      const shouldShowCollapsed = isLongOutput && !isToolOutputExpanded;
      
      // Also check if output content is long
      const isLongOutputContent = outputContent.length > 500;
      const shouldShowCollapsedOutput = isLongOutputContent && !isToolOutputExpanded;
      
      return (
        <div className="history-line">
          <div className="command-output-container">
            <div className="command-output-header">
                             <h3 className="command-title">{commandName.toUpperCase()}</h3>
              <div className="command-status">
                <div className="command-status-indicator"></div>
                <span>{item.status === 'completed' ? 'Completed' : item.status === 'error' ? 'Error' : 'Running'}</span>
              </div>
            </div>
            
            <div className={`command-output-content ${shouldShowCollapsed ? 'collapsed' : 'expanded'}`}>
              {formattedContent}
            </div>
            
            <div className="command-output-footer">
              <div className="command-output-length">
                <span>{formattedContent.length} characters</span>
                {isLongOutput && (
                  <span> • {shouldShowCollapsed ? 'Truncated' : 'Full output'}</span>
                )}
              </div>
              
              <div className="command-output-actions">
                {isLongOutput && (
                  <button 
                    className="command-action-button primary"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      startUserInteraction?.();
                      handleToolOutputToggle();
                    }}
                  >
                    {shouldShowCollapsed ? 'Show More' : 'Show Less'}
                  </button>
                )}
                <button 
                  className="command-action-button"
                  onClick={() => navigator.clipboard.writeText(formattedContent)}
                  title="Copy to clipboard"
                >
                  Copy
                </button>
              </div>
            </div>
          </div>
          
          {/* Show command output if available */}
          {outputContent && (
            <div className="tool-output-section">
              <div className="tool-output-header">
                <span className="tool-name">{commandName.toUpperCase()} OUTPUT</span>
                <div className="tool-status">
                  <div className="tool-status-indicator"></div>
                  <span>{item.status === 'completed' ? 'Completed' : item.status === 'error' ? 'Error' : 'Running'}</span>
                </div>
              </div>
              
              <div className={`tool-output-content ${shouldShowCollapsedOutput ? 'collapsed' : 'expanded'}`}>
                {outputContent}
              </div>
              
              <div className="tool-output-footer">
                <div className="tool-output-length">
                  <span>{outputContent.length} characters</span>
                  {isLongOutputContent && (
                    <span> • {shouldShowCollapsedOutput ? 'Truncated' : 'Full output'}</span>
                  )}
                </div>
                
                <div className="tool-output-actions">
                  {isLongOutputContent && (
                    <button 
                      className="tool-action-button primary"
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        startUserInteraction?.();
                        handleToolOutputToggle();
                      }}
                    >
                      {shouldShowCollapsedOutput ? 'Show More' : 'Show Less'}
                    </button>
                  )}
                  <button 
                    className="tool-action-button"
                    onClick={() => navigator.clipboard.writeText(outputContent)}
                    title="Copy to clipboard"
                  >
                    Copy
                  </button>
                </div>
              </div>
            </div>
          )}
          
          {responseItems.length > 0 && (
            <div className="agent-response">
              {responseItems.map((responseItem, i) => (
                <div key={`response-${i}`} className="response-item">
                  <MarkdownRenderer content={responseItem.content} />
                </div>
              ))}
            </div>
          )}
        </div>
      );
    }
    
    // Original progress item logic for non-$ commands
    const outputContent = item.output !== undefined && item.output !== null 
      ? (typeof item.output === 'object' ? JSON.stringify(item.output, null, 2) : String(item.output))
      : '';
    
    const isLongOutput = outputContent.length > 500;
    const shouldShowCollapsed = isLongOutput && !isToolOutputExpanded;
    
    return (
      <div className="history-line">
        <div className="progress-line">
          <span className="progress-content">
            {item.content}
          </span>
        </div>
        {outputContent && (
          <div className="tool-output-section">
            <div className="tool-output-header">
              <span className="tool-name">{item.toolName || 'Tool Output'}</span>
              <div className="tool-status">
                <div className="tool-status-indicator"></div>
                <span>{item.status === 'completed' ? 'Completed' : item.status === 'error' ? 'Error' : 'Running'}</span>
              </div>
            </div>
            
            <div className={`tool-output-content ${shouldShowCollapsed ? 'collapsed' : 'expanded'}`}>
              {outputContent}
            </div>
            
            <div className="tool-output-footer">
              <div className="tool-output-length">
                <span>{outputContent.length} characters</span>
                {isLongOutput && (
                  <span> • {shouldShowCollapsed ? 'Truncated' : 'Full output'}</span>
                )}
              </div>
              
              <div className="tool-output-actions">
                {isLongOutput && (
                  <button 
                    className="tool-action-button primary"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      startUserInteraction?.();
                      handleToolOutputToggle();
                    }}
                  >
                    {shouldShowCollapsed ? 'Show More' : 'Show Less'}
                  </button>
                )}
                <button 
                  className="tool-action-button"
                  onClick={() => navigator.clipboard.writeText(outputContent)}
                  title="Copy to clipboard"
                >
                  Copy
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }



  // Default text rendering (assistant responses)
  return (
    <div className="history-line">
      <div
        className="agent-response-wrapper"
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        <MarkdownRenderer content={item.content} />
        {isHovered && (
          <div className="message-actions">
            <button
              className="action-button copy-action"
              onClick={() => handleCopy(item.content)}
              title="Copy message"
            >
              📋
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

// Composant CommandInput intégré
const CommandInputComponent: React.FC<{
  input: string;
  isLoading: boolean;
  onInputChange: React.ChangeEventHandler<HTMLTextAreaElement>;
  onKeyDown: React.KeyboardEventHandler<HTMLTextAreaElement>;
  onPaste: React.ClipboardEventHandler<HTMLTextAreaElement>;
  onSubmit: () => void;
  terminalRef: React.RefObject<HTMLDivElement | null>;
  wasHiddenRef: React.RefObject<boolean>;
  lastVisibilityChangeRef: React.RefObject<number>;
}> = ({
  input,
  isLoading,
  onInputChange,
  onKeyDown,
  onPaste,
  onSubmit,
  terminalRef,
  wasHiddenRef,
  lastVisibilityChangeRef
}) => {
  if (isLoading) {
    return (
      <div className="prompt">
        <PromptSpinner />
      </div>
    );
  }

  const handleSend = () => {
    if (input.trim()) {
      onSubmit();
    }
  };

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
        spellCheck={false}
        placeholder="Type here (Shift+Enter for new line)"
        onFocus={() => {
          // Simple focus behavior - scroll to bottom if auto-scroll is enabled
          // BUT check if we recently came back from being hidden to prevent unwanted scroll
          const timeSinceVisibilityChange = Date.now() - lastVisibilityChangeRef.current;
          const wasRecentlyHidden = wasHiddenRef.current && timeSinceVisibilityChange < 600;

          if (terminalRef.current && !wasRecentlyHidden) {
            setTimeout(() => {
              terminalRef.current?.scrollTo({
                top: terminalRef.current.scrollHeight,
                behavior: 'smooth'
              });
            }, 50);
          }
        }}
      />
      <button
        className={`send-button ${isLoading ? 'sending' : ''}`}
        onClick={handleSend}
        disabled={!input.trim() || isLoading}
        title="Send message (Enter)"
      >
        {isLoading ? '⏳' : '➤'}
      </button>
    </div>
  );
};

const TerminalComponent: React.FC<TerminalProps> = ({
  history,
  input,
  isLoading,
  error,
  onInputChange,
  onKeyDown,
  onPaste,
  onSubmit,
  onRetry
}) => {
  const terminalRef = useRef<HTMLDivElement>(null);
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);
  const wasHiddenRef = useRef(false);
  const lastVisibilityChangeRef = useRef(0);

  // Simple scroll management - like a real terminal
  const scrollToBottom = useCallback(() => {
    if (terminalRef.current && shouldAutoScroll) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;

      // Remove scrolled-up class when auto-scrolling to bottom
      const prompt = document.querySelector('.prompt');
      if (prompt) {
        prompt.classList.remove('scrolled-up');
      }
    }
  }, [shouldAutoScroll]);

  // Check if user has manually scrolled up
  const handleScroll = useCallback(() => {
    if (terminalRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = terminalRef.current;
      const isAtBottom = scrollHeight - scrollTop - clientHeight < 10;
      setShouldAutoScroll(isAtBottom);
    }
  }, []);

  // Auto-scroll when new content is added
  useEffect(() => {
    // Check if we recently came back from being hidden - BEFORE calling scrollToBottom
    const timeSinceVisibilityChange = Date.now() - lastVisibilityChangeRef.current;
    const wasRecentlyHidden = wasHiddenRef.current && timeSinceVisibilityChange < 600;

    if (!wasRecentlyHidden) {
      scrollToBottom();
    }
  }, [history, scrollToBottom]);

  // Set up scroll event listener
  useEffect(() => {
    const terminal = terminalRef.current;
    if (terminal) {
      terminal.addEventListener('scroll', handleScroll);
      return () => terminal.removeEventListener('scroll', handleScroll);
    }
  }, [handleScroll]);

  // Handle scroll detection for prompt transparency
  useEffect(() => {
    const handlePromptScroll = () => {
      const prompt = document.querySelector('.prompt');
      if (prompt && terminalRef.current) {
        const { scrollTop, scrollHeight, clientHeight } = terminalRef.current;
        // Consider "scrolled up" when not at bottom (with 100px tolerance)
        const isScrolledUp = scrollTop < scrollHeight - clientHeight - 100;
        prompt.classList.toggle('scrolled-up', isScrolledUp);
      }
    };

    const terminal = terminalRef.current;
    if (terminal) {
      terminal.addEventListener('scroll', handlePromptScroll);
      // Initial check
      handlePromptScroll();
      return () => terminal.removeEventListener('scroll', handlePromptScroll);
    }
  }, []);

  // Handle tab/window focus changes to prevent unwanted auto-scroll
  useEffect(() => {
    const handleWindowBlur = () => {
      // Window/tab loses focus (user switched tabs or apps)
      wasHiddenRef.current = true;
    };

    const handleWindowFocus = () => {
      // Window/tab gains focus (user came back)
      lastVisibilityChangeRef.current = Date.now();

      // Clear the "was hidden" flag after some time to allow normal auto-scroll
      setTimeout(() => {
        wasHiddenRef.current = false;
      }, 500); // 500ms delay to prevent auto-scroll after focus change
    };

    // Use both visibilitychange AND focus/blur for better coverage
    const handleVisibilityChange = () => {
      if (document.hidden) {
        wasHiddenRef.current = true;
      } else {
        lastVisibilityChangeRef.current = Date.now();
        setTimeout(() => {
          wasHiddenRef.current = false;
        }, 500);
      }
    };

    window.addEventListener('blur', handleWindowBlur);
    window.addEventListener('focus', handleWindowFocus);
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      window.removeEventListener('blur', handleWindowBlur);
      window.removeEventListener('focus', handleWindowFocus);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

  const startUserInteraction = useCallback(() => {
    // Keep the startUserInteraction for the HistoryLine component compatibility
    // but don't use complex interaction detection anymore
  }, []);

  return (
    <div className="terminal">
      {/* TerminalContent intégré */}
      <div className={`terminal-content ${history.length > 0 ? 'has-content' : ''}`} ref={terminalRef}>
        {history.map((item, index) => (
          <div key={index}>
            <HistoryLine
              item={item}
              responseItems={[]}
              startUserInteraction={startUserInteraction}
              onRetry={onRetry}
            />
          </div>
        ))}
        
        {error && <div className="error">{error}</div>}
        
        <CommandInput
          input={input}
          isLoading={isLoading}
          onInputChange={onInputChange}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
          onSubmit={onSubmit}
          terminalRef={terminalRef}
          wasHiddenRef={wasHiddenRef}
          lastVisibilityChangeRef={lastVisibilityChangeRef}
        />
      </div>
    </div>
  );
};

const HistoryLine = memo(HistoryLineComponent);
const CommandInput = memo(CommandInputComponent);
export const Terminal = memo(TerminalComponent); 