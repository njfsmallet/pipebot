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
import { User, HistoryItem, ServerResponse, StreamUpdate } from './types'

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
  setHiddenOutputs: React.Dispatch<React.SetStateAction<Set<number | string>>>,
  currentHistoryLength: number
) => {
  messages?.forEach((message) => {
    try {
      if (message.role === "assistant" || message.role === "user") {
        const content = message.content;
        if (Array.isArray(content)) {
          content.forEach((item) => {
            if (item.type === "text") {
              const text = typeof item.content === 'string' ? item.content.trim() : '';
              if (text) {
                addToHistory({ type: 'text', content: text });
                  
                if (text.startsWith('$')) {
                  const newIndex = currentHistoryLength;
                  setHiddenOutputs(prev => {
                    const newSet = new Set(prev);
                    newSet.add(`sys-${newIndex}`);
                    return newSet;
                  });
                }
              }
            } else if (item.type === "toolUse") {
              const command = `$ ${item.tool} ${item.command}`;
              addToHistory({ type: 'text', content: command });
              const newIndex = currentHistoryLength;
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
    } catch (error) {
      throw error;
    }
  });
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
  const [currentProgressIndex, setCurrentProgressIndex] = useState<number | null>(null);
  const currentProgressIndexRef = useRef<number | null>(null);
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
   * Handles streaming updates from the server
   */
  const handleStreamUpdate = (update: StreamUpdate) => {
    switch (update.type) {
      case 'status':
        if (currentProgressIndex !== null) {
          setHistory(prev => {
            const newHistory = [...prev];
            newHistory[currentProgressIndex] = {
              type: 'progress',
              content: update.message || 'Processing...',
              status: 'running'
            };
            return newHistory;
          });
        } else {
          setHistory(prev => {
            const newIndex = prev.length;
            setCurrentProgressIndex(newIndex);
            currentProgressIndexRef.current = newIndex;
            return [...prev, {
              type: 'progress',
              content: update.message || 'Processing...',
              status: 'running'
            }];
          });
        }
        break;
        
      case 'tool_start': {
        setHistory(prev => {
          const toolStartIndex = prev.length;
          setCurrentProgressIndex(toolStartIndex);
          currentProgressIndexRef.current = toolStartIndex;
          return [...prev, {
            type: 'progress',
            content: `$ ${update.tool_name} ${update.command}`,
            toolName: update.tool_name,
            status: 'running'
          }];
        });
        break;
      }
        
      case 'tool_result':
        if (currentProgressIndexRef.current !== null) {
          const progressIndex = currentProgressIndexRef.current;
          setHistory(prev => {
            const newHistory = [...prev];
            const currentItem = newHistory[progressIndex];
            // Update the status and add the output to the progress item
            const updatedItem = {
              ...currentItem,
              status: (update.success ? 'completed' : 'error') as 'completed' | 'error',
              output: update.success ? update.output : update.error
            };
            newHistory[progressIndex] = updatedItem;
            return newHistory;
          });
        }
        break;
        
      case 'conversation':
        setHistory(prev => {
          try {
            const newItems: HistoryItem[] = [];
            
            const addToHistoryFunction = (item: HistoryItem) => {
              newItems.push(item);
            };
            
            processConversationMessages(update.messages, 
              addToHistoryFunction,
              setHiddenOutputs,
              prev.length
            );
            
            return [...prev, ...newItems];
          } catch (error) {
            return prev; // Return previous state on error
          }
        });
        setCurrentProgressIndex(null);
        currentProgressIndexRef.current = null;
        setIsLoading(false);
        break;
        
      case 'assistant_response':
        // Add the assistant response to history
        if (update.response && typeof update.response === 'string' && update.response.trim()) {
          setHistory(prev => [...prev, {
            type: 'text',
            content: update.response!.trim()
          }]);
        } else {
          // Wait a bit for a potential conversation message
          setTimeout(() => {
            setCurrentProgressIndex(null);
            currentProgressIndexRef.current = null;
            setIsLoading(false);
          }, 1000);
          return; // Don't cleanup immediately
        }
        
        setCurrentProgressIndex(null);
        currentProgressIndexRef.current = null;
        setIsLoading(false);
        break;
        
      case 'error':
        setError(update.message || 'An error occurred');
        setCurrentProgressIndex(null);
        currentProgressIndexRef.current = null;
        setIsLoading(false);
        break;
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
      setError(null);
      
      try {
        await sendStreamingRequest(command, undefined, handleStreamUpdate);
      } catch (err) {
        console.error('Error:', err);
        setError('Error processing your request. Please check if the backend server is running.');
        setIsLoading(false);
      } finally {
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
                await sendStreamingRequest(imageDescription, { base64Data, type: file.type }, handleStreamUpdate);
              } catch (err) {
                console.error('Error:', err);
                setError('Error processing your request. Please check if the backend server is running.');
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


  /**
   * Sends streaming request to server
   * @param command - Command to send
   * @param image - Optional image data
   * @param onUpdate - Callback for streaming updates
   */
  const sendStreamingRequest = async (
    command: string, 
    image: { base64Data: string; type: string } | undefined,
    onUpdate: (update: StreamUpdate) => void
  ) => {
    const requestBody = image ? { 
      command,
      image: image.base64Data,
      imageType: image.type
    } : { 
      command
    };
    
    try {
      const response = await fetch(API_ENDPOINTS.converseStream, {
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

      if (!response.body) {
        throw new Error('No response body');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      
      while (true) {
        const { done, value } = await reader.read();
        
        if (done) break;
        
        // Accumulate chunks in buffer to handle fragmented data
        buffer += decoder.decode(value, { stream: true });
        
        // Process complete lines
        const lines = buffer.split('\n');
        // Keep the last potentially incomplete line in buffer
        buffer = lines.pop() || '';
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              onUpdate(data);
            } catch (e) {
              console.error('Error parsing streaming data:', e);
              console.error('Problematic line:', line);
            }
          }
        }
      }
      
      // Process any remaining data in buffer
      if (buffer.startsWith('data: ')) {
        try {
          const data = JSON.parse(buffer.slice(6));
          onUpdate(data);
        } catch (e) {
          console.error('Error parsing final streaming data:', e);
        }
      }
    } catch (error: unknown) {
      if (error instanceof Error) {
        onUpdate({ type: 'error', message: error.message });
      } else {
        onUpdate({ type: 'error', message: 'An unknown error occurred' });
      }
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
        history={history}
        input={input}
        isLoading={isLoading}
        error={error}
        hiddenOutputs={hiddenOutputs}
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