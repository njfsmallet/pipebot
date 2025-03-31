/**
 * @fileoverview Main application component for the terminal-like interface
 * @module App
 */

import { useState, useEffect, KeyboardEvent, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import './App.css'
import React from 'react'
import { API_ENDPOINTS } from './config/api'

/**
 * Represents the result of a command execution
 */
interface CommandResult {
  text: string;
}

/**
 * Props for code block components
 */
interface CodeProps extends React.HTMLAttributes<HTMLElement> {
  inline?: boolean;
  children?: React.ReactNode;
}

/**
 * Props for markdown components
 */
interface MarkdownComponentProps {
  children?: React.ReactNode;
  [key: string]: any;
}

/**
 * Represents a code element in React
 */
interface CodeElement extends React.ReactElement {
  type: string;
  props: {
    inline?: boolean;
    [key: string]: any;
  };
}

/**
 * Represents an item in the conversation history
 */
interface HistoryItem {
  type: 'text' | 'image';
  content: string;
  imageData?: string;
}

/**
 * Represents the content of a message
 */
interface MessageContent {
  type: string;
  content: string | CommandResult[];
  tool?: string;
  command?: string;
  format?: string;
}

/**
 * Represents a message from the server
 */
interface ServerMessage {
  role: string;
  content: string | MessageContent[];
}

/**
 * Represents a response from the server
 */
interface ServerResponse {
  output?: string;
  type?: string;
  messages?: ServerMessage[];
}

type HistoryState = HistoryItem[];

interface User {
  name: string;
  email: string;
  roles: string[];
}

interface SmartModeState {
  isEnabled: boolean;
  lastToggle: number;
}

/**
 * Checks if text contains a code block
 * @param text - Text to check
 * @returns True if text contains code block
 */
const containsCodeBlock = (text: string): boolean => {
  const codePatterns = [
    /```[\s\S]*?```/,
    /\$\s*[\w\-\s]+/,
  ];
  
  return codePatterns.some(pattern => pattern.test(text));
};

/**
 * Adjusts textarea height based on content
 * @param textarea - Textarea element to adjust
 */
const adjustTextareaHeight = (textarea: HTMLTextAreaElement) => {
  // Reset height to auto to get the correct scrollHeight
  textarea.style.height = 'auto';
  
  // Calculate the new height, but cap it at 200px
  const newHeight = Math.min(textarea.scrollHeight, 200);
  textarea.style.height = `${newHeight}px`;
  
  // Add or remove the scrollable class based on content height
  if (textarea.scrollHeight > 200) {
    textarea.classList.add('scrollable');
  } else {
    textarea.classList.remove('scrollable');
  }
};

/**
 * Copies text to clipboard
 * @param text - Text to copy
 */
const copyToClipboard = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text);
  } catch (err) {
    console.error('Failed to copy text: ', err);
  }
};

/**
 * Custom text renderer component for markdown
 * @param props - Component props
 */
const TextRenderer = ({ children, ...props }: MarkdownComponentProps) => {
  if (typeof children === 'string') {
    const hasCode = containsCodeBlock(children);
    return <div className={hasCode ? "text-block" : "text-line"} {...props}>{children}</div>;
  }

  const childrenArray = React.Children.toArray(children);
  const hasCodeBlock = childrenArray.some(
    child => React.isValidElement(child) && 
    ((child as CodeElement).type === 'code' || 
     (typeof child === 'string' && containsCodeBlock(child)))
  );

  return <div className={hasCodeBlock ? "text-block" : "text-line"} {...props}>{children}</div>;
};

/**
 * Processes conversation messages and updates history
 * @param messages - Messages to process
 * @param setHistory - History state setter
 */
const processConversationMessages = (messages: ServerResponse['messages'], setHistory: React.Dispatch<React.SetStateAction<HistoryState>>) => {
  messages?.forEach(message => {
    if (message.role === "assistant" || message.role === "user") {
      const content = message.content;
      if (Array.isArray(content)) {
        content.forEach(item => {
          if (item.type === "text") {
            const text = typeof item.content === 'string' ? item.content.trim() : '';
            setHistory(prev => [...prev, { type: 'text', content: text }]);
          } else if (item.type === "toolUse") {
            const command = `$ ${item.tool} ${item.command}`;
            setHistory(prev => [...prev, { type: 'text', content: command }]);
          } else if (item.type === "toolResult") {
            const toolOutput = Array.isArray(item.content) 
              ? item.content.map((result: CommandResult) => result.text).join("\n").trim()
              : typeof item.content === 'string' ? item.content.trim() : '';
            if (toolOutput) {
              setHistory(prev => [...prev, { type: 'text', content: toolOutput }]);
            }
          }
        });
      } else if (typeof content === "string" && content.trim()) {
        setHistory(prev => [...prev, { type: 'text', content: content.trim() }]);
      }
    }
  });
};

/**
 * Processes server response and updates history
 * @param data - Response data from server
 * @param setHistory - History state setter
 */
const processServerResponse = (data: ServerResponse, setHistory: React.Dispatch<React.SetStateAction<HistoryState>>) => {
  if (data.output) {
    try {
      const outputData = JSON.parse(data.output);
      if (outputData.type === "conversation" && outputData.messages) {
        processConversationMessages(outputData.messages, setHistory);
      } else {
        setHistory(prev => [...prev, { type: 'text', content: data.output! }]);
      }
    } catch {
      setHistory(prev => [...prev, { type: 'text', content: data.output! }]);
    }
  } else if (data.type === "conversation" && data.messages) {
    processConversationMessages(data.messages, setHistory);
  } else if (data.output) {
    setHistory(prev => [...prev, { type: 'text', content: data.output! }]);
  } else {
    setHistory(prev => [...prev, { type: 'text', content: JSON.stringify(data, null, 2) }]);
  }
};

/**
 * Main App component that manages the terminal-like interface
 * @component
 * @returns {JSX.Element} The rendered App component
 */
function App() {
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [input, setInput] = useState<string>('')
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState<boolean>(false)
  const [hiddenOutputs, setHiddenOutputs] = useState<Set<number | string>>(new Set());
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [user, setUser] = useState<User | null>(null);
  const [smartMode, setSmartMode] = useState<SmartModeState>({ isEnabled: false, lastToggle: 0 });
  const terminalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    checkAuth();
    // Check for error in URL parameters
    const params = new URLSearchParams(window.location.search);
    const errorParam = params.get('error');
    if (errorParam) {
      setError(decodeURIComponent(errorParam));
      // Clear error from URL
      window.history.replaceState({}, '', '/');
    }
  }, []);

  const checkAuth = async () => {
    try {
      const response = await fetch(API_ENDPOINTS.auth.user);
      if (response.ok) {
        const userData = await response.json();
        setUser(userData);
        setIsAuthenticated(true);
        setError(null);
      } else {
        const errorData = await response.json();
        setIsAuthenticated(false);
        setUser(null);
        setError(errorData.detail || 'Authentication failed');
      }
    } catch (error) {
      console.error('Auth check failed:', error);
      setIsAuthenticated(false);
      setUser(null);
      setError('Failed to check authentication status');
    }
  };

  const handleLogin = () => {
    setError(null);
    window.location.href = API_ENDPOINTS.auth.login;
  };

  const handleLogout = async () => {
    try {
      await fetch(API_ENDPOINTS.auth.logout);
      
      // Mettre à jour l'état
      setIsAuthenticated(false);
      setUser(null);
      setError(null);
      
      // Rediriger vers la page d'accueil
      window.location.href = '/';
    } catch (error) {
      console.error('Logout failed:', error);
      setError('Failed to logout');
    }
  };

  /**
   * Effect hook to clear conversation on mount
   */
  useEffect(() => {
    const clearConversation = async () => {
      try {
        const response = await fetch(API_ENDPOINTS.clear, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          }
        });
        
        if (!response.ok) {
          const errorData = await response.json();
          console.error('Error clearing conversation:', errorData);
        }
      } catch (error) {
        console.error('Error calling clear API:', error);
      }
    };

    clearConversation();
    setHistory([]);
    setHiddenOutputs(new Set());
  }, []);

  /**
   * Effect hook to scroll terminal to bottom when history changes
   */
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [history]);

  /**
   * Handles keyboard events in the input textarea
   * @param {KeyboardEvent<HTMLTextAreaElement>} e - Keyboard event
   */
  const handleKeyDown = async (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter') {
      if (e.shiftKey) {
        e.preventDefault();
        const textarea = e.currentTarget;
        const cursorPosition = textarea.selectionStart;
        const newValue = input.slice(0, cursorPosition) + '\n' + input.slice(cursorPosition);
        setInput(newValue);
        
        requestAnimationFrame(() => {
          adjustTextareaHeight(textarea);
          textarea.selectionStart = cursorPosition + 1;
          textarea.selectionEnd = cursorPosition + 1;
        });
        return;
      }

      e.preventDefault();
      const command = input.trim();
      if (!command) return;
      
      setHistory(prev => [...prev, { type: 'text', content: `>_ ${command}` }]);
      setIsLoading(true);
      
      try {
        const data = await sendRequest(command);
        processServerResponse(data, setHistory);
        setError(null);
      } catch (err) {
        console.error('Error:', err);
        setError('Error processing your request. Please check if the backend server is running.');
      } finally {
        setIsLoading(false);
        setInput('');
      }
    }
  };

  /**
   * Handles changes in the input textarea
   * @param {React.ChangeEvent<HTMLTextAreaElement>} e - Change event
   */
  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    adjustTextareaHeight(e.target);
  };

  /**
   * Handles paste events in the input textarea
   * @param {React.ClipboardEvent<HTMLTextAreaElement>} e - Clipboard event
   */
  const handlePaste = async (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const items = e.clipboardData.items;
    
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        e.preventDefault();
        const file = item.getAsFile();
        
        if (file) {
          try {
            setIsLoading(true);
            const reader = new FileReader();
            reader.onload = async (event) => {
              const base64Image = event.target?.result as string;
              const base64Data = base64Image.split(',')[1];
              
              const imageDescription = input.trim() || 'Analyse cette image';
              
              setInput('');
              
              setHistory(prev => [...prev, {
                type: 'image',
                content: imageDescription,
                imageData: base64Image
              }]);

              try {
                const data = await sendRequest(imageDescription, { base64Data, type: file.type });
                processServerResponse(data, setHistory);
              } catch (err) {
                console.error('Error:', err);
                setError('Error processing your request. Please check if the backend server is running.');
              } finally {
                setIsLoading(false);
              }
            };
            reader.readAsDataURL(file);
          } catch (error) {
            console.error('Error processing pasted image:', error);
            setError('Error processing the pasted image.');
            setIsLoading(false);
          }
        }
        break;
      }
    }
  };

  /**
   * Toggles visibility of command output
   * @param {number|string} index - Index or ID of the command output to toggle
   */
  const toggleCommandOutput = (index: number | string) => {
    setHiddenOutputs(prev => {
      const newSet = new Set(prev);
      if (newSet.has(index)) {
        newSet.delete(index);
      } else {
        newSet.add(index);
      }
      return newSet;
    });
  };

  const toggleSmartMode = () => {
    const now = Date.now();
    if (now - smartMode.lastToggle < 500) return; // Prevent rapid toggling
    
    setSmartMode(prev => ({
      isEnabled: !prev.isEnabled,
      lastToggle: now
    }));
  };

  /**
   * Sends request to server
   * @param command - Command to send
   * @param image - Optional image data
   * @returns Server response
   */
  const sendRequest = async (command: string, image?: { base64Data: string; type: string }) => {
    const requestBody = image ? { 
      command,
      image: image.base64Data,
      imageType: image.type,
      smartMode: smartMode.isEnabled
    } : { 
      command,
      smartMode: smartMode.isEnabled
    };
    
    try {
      const response = await fetch(API_ENDPOINTS.converse, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestBody)
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || `Server error: ${response.status}`);
      }

      const data = await response.json();
      return data;
    } catch (error: unknown) {
      if (error instanceof Error) {
        throw error;
      }
      throw new Error('An unknown error occurred');
    }
  };

  /**
   * Custom components for markdown rendering
   * @type {Object} Markdown component definitions
   */
  const markdownComponents = {
    h1: ({ children, ...props }: MarkdownComponentProps) => <h1 className="markdown-heading" {...props}>{children}</h1>,
    h2: ({ children, ...props }: MarkdownComponentProps) => <h2 className="markdown-heading" {...props}>{children}</h2>,
    h3: ({ children, ...props }: MarkdownComponentProps) => <h3 className="markdown-heading" {...props}>{children}</h3>,
    ul: ({ children, ...props }: MarkdownComponentProps) => <ul className="markdown-list" {...props}>{children}</ul>,
    li: ({ children, ...props }: MarkdownComponentProps) => <li className="list-item" {...props}>{children}</li>,
    p: TextRenderer,
    code: ({inline, className, children, ...props}: CodeProps) => {
      const match = /language-(\w+)/.exec(className || '');
      const language = match ? match[1] : '';
      
      return inline ? (
        <code className="inline-code" {...props}>
          {children}
        </code>
      ) : language ? (
        <div className="code-block-wrapper">
          <div className="code-block-header">
            <span className="code-language">{language}</span>
            <button 
              className="copy-button"
              onClick={() => copyToClipboard(String(children))}
              title="Copy to clipboard"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
              </svg>
            </button>
          </div>
          <code className={`code-block language-${language}`} {...props}>
            {children}
          </code>
        </div>
      ) : (
        <code className="simple-code-block" {...props}>
          {children}
        </code>
      );
    }
  };

  /**
   * Formats output for display
   * @param {HistoryItem} item - History item to format
   * @param {number} index - Index of the item in history
   * @returns {JSX.Element|null} Formatted output element or null
   */
  const formatOutput = (item: HistoryItem, index: number) => {
    if (item.type === 'image') {
      return (
        <div className="image-paste-indicator">
          <img 
            src={item.imageData} 
            alt="Thumbnail" 
            className="image-thumbnail"
          />
          <span className="image-text">{item.content}</span>
        </div>
      );
    }

    const line = item.content;

    if (line.startsWith('$')) {
      return null;
    }

    if (index > 0 && history[index-1].type === 'text' && history[index-1].content.startsWith('$')) {
      return null;
    }

    try {
      const data = JSON.parse(line);
      if (data.type === "conversation" && data.messages) {
        return (
          <>
            {data.messages.map((message: ServerMessage, msgIndex: number) => {
              if (message.content && Array.isArray(message.content)) {
                return message.content.map((content: MessageContent, contentIndex: number) => {
                  if (content.type === "text") {
                    const decodedContent = typeof content.content === 'string' 
                      ? content.content
                          .replace(/\\n/g, '\n')
                          .split('\n')
                          .map((line: string) => line.replace(/\s+/g, ' ').trim())
                          .join('\n')
                          .replace(/\n{3,}/g, '\n\n')
                      : '';
                    
                    return (
                      <div key={`message-${msgIndex}-content-${contentIndex}`} className="message-content">
                        <ReactMarkdown components={markdownComponents}>
                          {decodedContent}
                        </ReactMarkdown>
                      </div>
                    );
                  } else if (content.type === "image") {
                    return (
                      <div key={`message-${msgIndex}-content-${contentIndex}`} className="message-content">
                        <img 
                          src={`data:image/${content.format};base64,${content.content}`}
                          alt="Generated or pasted image"
                          className="conversation-image"
                        />
                      </div>
                    );
                  }
                  return null;
                });
              }
              return null;
            })}
          </>
        );
      }
      return <div className="text-output">{data.output}</div>;
    } catch {
      const cleanedLine = line
        .split('\n')
        .map((line: string) => {
          const leadingSpaces = line.match(/^[\s\t]+/)?.[0] || '';
          const cleanedContent = line.replace(/^[\s\t]+/, '').replace(/\s+$/, '');
          return leadingSpaces + cleanedContent;
        })
        .join('\n')
        .replace(/\n{3,}/g, '\n\n');

      return (
        <div className="text-output">
          <ReactMarkdown components={markdownComponents}>
            {cleanedLine}
          </ReactMarkdown>
        </div>
      );
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="App">
        <div className="login-container">
          <h1>PipeBot</h1>
          <p>Please sign in to continue</p>
          {error && <div className="error-message">{error}</div>}
          <button onClick={handleLogin} className="login-button">
            Sign in with Microsoft
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="App">
      <div className="terminal">
        <div className="terminal-header">
          <div className="header-left">
            <button 
              className={`smart-mode-toggle ${smartMode.isEnabled ? 'active' : ''}`}
              onClick={toggleSmartMode}
              title={smartMode.isEnabled ? "Disable Smart Mode" : "Enable Smart Mode"}
            >
              <div className="smart-mode-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
                </svg>
              </div>
            </button>
          </div>
          <div className="user-info">
            {user && (
              <>
                <span>{user.name}</span>
                <button onClick={handleLogout} className="logout-button" title="Sign out">
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
        <div className="terminal-content" ref={terminalRef}>
          {history.map((item, index) => {
            if (item.type === 'text' && item.content.startsWith('>_')) {
              let responseEndIndex = index + 1;
              while (
                responseEndIndex < history.length && 
                !(history[responseEndIndex].type === 'text' && history[responseEndIndex].content.startsWith('>_'))
              ) {
                responseEndIndex++;
              }
              
              const responseItems = history.slice(index + 1, responseEndIndex);
              
              return (
                <div key={index} className="history-line">
                  <div 
                    className="command-line" 
                    onClick={() => toggleCommandOutput(index)}
                  >
                    {item.content}
                  </div>
                  <div className={`agent-response ${hiddenOutputs.has(index) ? 'hidden' : ''}`}>
                    {responseItems.map((responseItem, i) => {
                      if (responseItem.type === 'text' && responseItem.content.startsWith('$')) {
                        const nextLineIndex = index + i + 2;
                        const nextLine = nextLineIndex < history.length ? history[nextLineIndex] : null;
                        const hasOutput = nextLine && 
                                      nextLine.type === 'text' && 
                                      !nextLine.content.startsWith('$') && 
                                      !nextLine.content.startsWith('>_');
                        
                        const commandId = `cmd-${index}-${i}`;
                        
                        return (
                          <div key={`system-command-${i}`} className="system-command-group">
                            <div 
                              className="command-line" 
                              onClick={() => toggleCommandOutput(commandId)}
                              style={{ cursor: 'pointer' }}
                            >
                              {responseItem.content}
                            </div>
                            {hasOutput && (
                              <div className={`command-output ${!hiddenOutputs.has(commandId) ? 'hidden' : ''}`}>
                                {nextLine!.content}
                              </div>
                            )}
                          </div>
                        );
                      }
                      
                      if (i > 0 && 
                          responseItems[i-1].type === 'text' && 
                          responseItems[i-1].content.startsWith('$') &&
                          !responseItem.content.startsWith('$') &&
                          !responseItem.content.startsWith('>_')) {
                        return null;
                      }
                      
                      const output = formatOutput(responseItem, index + i + 1);
                      return output ? (
                        <div key={`response-${i}`} className="response-item">
                          {output}
                        </div>
                      ) : null;
                    })}
                  </div>
                </div>
              );
            }
            else if (item.type === 'text' && item.content.startsWith('$')) {
              const nextLine = index + 1 < history.length ? history[index + 1] : null;
              const hasOutput = nextLine && 
                              nextLine.type === 'text' && 
                              !nextLine.content.startsWith('$') && 
                              !nextLine.content.startsWith('>_');
              
              const previousLines = history.slice(0, index);
              const lastCommand = previousLines.reverse().find(item => 
                item.type === 'text' && item.content.startsWith('>_')
              );
              
              if (lastCommand) {
                return null;
              }
              
              const commandId = `sys-${index}`;
              
              return (
                <div key={index} className="history-line">
                  <div 
                    className="command-line" 
                    onClick={() => toggleCommandOutput(commandId)}
                    style={{ cursor: 'pointer' }}
                  >
                    {item.content}
                  </div>
                  {hasOutput && (
                    <div className={`command-output ${!hiddenOutputs.has(commandId) ? 'hidden' : ''}`}>
                      {nextLine!.content}
                    </div>
                  )}
                </div>
              );
            }
            else {
              const previousLines = history.slice(0, index);
              const lastCommand = previousLines.reverse().find(item => 
                item.type === 'text' && item.content.startsWith('>_')
              );
              
              if (lastCommand) {
                return null;
              }
              
              if (index > 0 && 
                  history[index-1].type === 'text' && 
                  history[index-1].content.startsWith('$')) {
                return null;
              }
              
              const output = formatOutput(item, index);
              return output ? (
                <div key={index} className="history-line">
                  {output}
                </div>
              ) : null;
            }
          })}
          
          {error && <div className="error">{error}</div>}
        </div>
        
        {isLoading ? (
          <div className="loading-indicator">▋</div>
        ) : (
          <div className="prompt">
            <span>&gt;_</span>
            <textarea
              className="input-line"
              value={input}
              onChange={handleChange}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              rows={1}
              autoFocus
            />
          </div>
        )}
      </div>
    </div>
  )
}

export default App
