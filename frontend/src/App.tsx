/**
 * @fileoverview Main application component for the terminal-like interface
 * @module App
 */

import { useState, useEffect, KeyboardEvent, useRef } from 'react'
import './styles/index.css'
import React from 'react'
import { API_ENDPOINTS } from './config/api'
import { Terminal } from './components/Terminal'
import { LoginScreen } from './components/LoginScreen'
import { User, HistoryItem, ServerResponse, SmartModeState } from './types'

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
 * Processes conversation messages and updates history
 * @param messages - Messages to process
 * @param addToHistory - Function to add item to history
 */
const processConversationMessages = (
  messages: ServerResponse['messages'],
  addToHistory: (item: HistoryItem) => void,
  setHiddenOutputs: React.Dispatch<React.SetStateAction<Set<number | string>>>
) => {
  messages?.forEach(message => {
    if (message.role === "assistant" || message.role === "user") {
      const content = message.content;
      if (Array.isArray(content)) {
        content.forEach(item => {
          if (item.type === "text") {
            const text = typeof item.content === 'string' ? item.content.trim() : '';
            const newIndex = history.length;
            addToHistory({ type: 'text', content: text });
            if (text.startsWith('$')) {
              setHiddenOutputs(prev => {
                const newSet = new Set(prev);
                newSet.add(`sys-${newIndex}`);
                return newSet;
              });
            }
          } else if (item.type === "toolUse") {
            const command = `$ ${item.tool} ${item.command}`;
            const newIndex = history.length;
            addToHistory({ type: 'text', content: command });
            setHiddenOutputs(prev => {
              const newSet = new Set(prev);
              newSet.add(`sys-${newIndex}`);
              return newSet;
            });
          } else if (item.type === "toolResult") {
            const toolOutput = Array.isArray(item.content) 
              ? item.content.map(result => result.text).join("\n").trim()
              : typeof item.content === 'string' ? item.content.trim() : '';
            if (toolOutput) {
              addToHistory({ type: 'text', content: toolOutput });
            }
          }
        });
      } else if (typeof content === "string" && content.trim()) {
        addToHistory({ type: 'text', content: content.trim() });
      }
    }
  });
};

/**
 * Processes server response and updates history
 * @param data - Response data from server
 * @param setHistory - History state setter
 * @param setHiddenOutputs - Hidden outputs state setter
 */
const processServerResponse = (
  data: ServerResponse,
  setHistory: React.Dispatch<React.SetStateAction<HistoryItem[]>>,
  setHiddenOutputs: React.Dispatch<React.SetStateAction<Set<number | string>>>
) => {
  if (data.output) {
    try {
      const outputData = JSON.parse(data.output);
      if (outputData.type === "conversation" && outputData.messages) {
        processConversationMessages(outputData.messages, 
          (item) => setHistory(prev => [...prev, item]),
          setHiddenOutputs
        );
      } else {
        setHistory(prev => [...prev, { type: 'text', content: data.output! }]);
      }
    } catch {
      setHistory(prev => [...prev, { type: 'text', content: data.output! }]);
    }
  } else if (data.type === "conversation" && data.messages) {
    processConversationMessages(data.messages, 
      (item) => setHistory(prev => [...prev, item]),
      setHiddenOutputs
    );
  } else if (data.output) {
    setHistory(prev => [...prev, { type: 'text', content: data.output! }]);
  } else if (data.messages) {
    processConversationMessages(data.messages, 
      (item) => setHistory(prev => [...prev, item]),
      setHiddenOutputs
    );
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
  const initializedRef = useRef<boolean>(false);

  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;

    const initializeApp = async () => {
      // Check authentication
      await checkAuth();
      
      // Check for error in URL parameters
      const params = new URLSearchParams(window.location.search);
      const errorParam = params.get('error');
      if (errorParam) {
        setError(decodeURIComponent(errorParam));
        // Clear error from URL
        window.history.replaceState({}, '', '/');
      }

      // Clear conversation
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

      setHistory([]);
      setHiddenOutputs(new Set());
    };

    initializeApp();
  }, []); // Empty dependency array since we only want this to run once on mount

  /**
   * Effect hook to scroll terminal to bottom when history changes
   */
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [history]);

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
      
      // Update state
      setIsAuthenticated(false);
      setUser(null);
      setError(null);
      
      // Redirect to home page
      window.location.href = '/';
    } catch (error) {
      console.error('Logout failed:', error);
      setError('Failed to logout');
    }
  };

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
      
      const newIndex = history.length;
      setHistory(prev => [...prev, { type: 'text', content: `>_ ${command}` }]);
      setHiddenOutputs(prev => {
        const newSet = new Set(prev);
        newSet.add(newIndex);
        return newSet;
      });
      setIsLoading(true);
      
      try {
        const data = await sendRequest(command);
        processServerResponse(data, setHistory, setHiddenOutputs);
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

              const newIndex = history.length + 1;
              setHistory(prev => [...prev, 
                {
                  type: 'image',
                  content: imageDescription,
                  imageData: base64Image
                },
                { 
                  type: 'text', 
                  content: `>_ ${imageDescription}` 
                }
              ]);
              
              setHiddenOutputs(prev => {
                const newSet = new Set(prev);
                newSet.add(newIndex);
                return newSet;
              });

              try {
                const data = await sendRequest(imageDescription, { base64Data, type: file.type });
                processServerResponse(data, setHistory, setHiddenOutputs);
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
      if (!newSet.has(index)) {
        newSet.add(index);
      } else {
        newSet.delete(index);
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

  if (!isAuthenticated) {
    return (
      <div className="App">
        <LoginScreen error={error} onLogin={handleLogin} />
      </div>
    );
  }

  return (
    <div className="App">
      <Terminal
        user={user}
        smartMode={smartMode}
        history={history}
        input={input}
        isLoading={isLoading}
        error={error}
        hiddenOutputs={hiddenOutputs}
        onToggleSmartMode={toggleSmartMode}
        onLogout={handleLogout}
        onToggleOutput={toggleCommandOutput}
        onInputChange={handleChange}
        onKeyDown={handleKeyDown}
        onPaste={handlePaste}
      />
    </div>
  )
}

export default App
