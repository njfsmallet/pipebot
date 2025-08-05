import { useState, useRef, useCallback, useMemo } from 'react';
import { HistoryItem, StreamUpdate } from '../types';
import { API_ENDPOINTS } from '../config/api';

export const useStreaming = () => {
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [currentProgressIndex, setCurrentProgressIndex] = useState<number | null>(null);
  const currentProgressIndexRef = useRef<number | null>(null);

  /**
   * Processes conversation messages and updates history
   */
  const processConversationMessages = (
    messages: unknown,
    addToHistory: (item: HistoryItem) => void
  ) => {
    if (!Array.isArray(messages)) return;
    
    messages.forEach((message: unknown) => {
      if (typeof message === 'object' && message && 'role' in message && 'content' in message) {
        const content = (message as { content: unknown }).content;
        if (Array.isArray(content)) {
                      content.forEach((item: unknown) => {
              if (typeof item === 'object' && item && 'type' in item) {
                const itemType = (item as { type: string }).type;
                if (itemType === "text" && 'content' in item) {
                  const text = typeof (item as { content: unknown }).content === 'string' ? (item as { content: string }).content.trim() : '';
                  if (text) {
                    addToHistory({ type: 'text', content: text });
                  }
                } else if (itemType === "toolUse" && 'command' in item) {
                  addToHistory({ type: 'text', content: (item as { command?: string }).command || '' });
                } else if (itemType === "toolResult" && 'content' in item) {
                  const itemContent = (item as { content: unknown }).content;
                  const toolOutput = Array.isArray(itemContent) 
                    ? itemContent.map((result: unknown) => typeof result === 'object' && result && 'text' in result ? (result as { text: string }).text : '').join("\n").trim()
                    : typeof itemContent === 'string' ? itemContent.trim() : '';
                  if (toolOutput) {
                    addToHistory({ type: 'text', content: toolOutput });
                  }
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
            
            processConversationMessages(update.messages, addToHistoryFunction);
            
            return [...prev, ...newItems];
          } catch {
            return prev;
          }
        });
        setCurrentProgressIndex(null);
        currentProgressIndexRef.current = null;
        setIsLoading(false);
        break;
        
      case 'assistant_response':
        if (update.response && typeof update.response === 'string' && update.response.trim()) {
          setHistory(prev => [...prev, {
            type: 'text',
            content: update.response!.trim()
          }]);
        } else {
          setTimeout(() => {
            setCurrentProgressIndex(null);
            currentProgressIndexRef.current = null;
            setIsLoading(false);
          }, 1000);
          return;
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
   * Sends streaming request to server
   */
  const sendStreamingRequest = async (
    command: string, 
    image: { base64Data: string; type: string } | undefined
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
        
        buffer += decoder.decode(value, { stream: true });
        
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              handleStreamUpdate(data);
            } catch (e) {
              console.error('Error parsing streaming data:', e);
              console.error('Problematic line:', line);
            }
          }
        }
      }
      
      if (buffer.startsWith('data: ')) {
        try {
          const data = JSON.parse(buffer.slice(6));
          handleStreamUpdate(data);
        } catch (e) {
          console.error('Error parsing final streaming data:', e);
        }
      }
    } catch (error: unknown) {
      if (error instanceof Error) {
        handleStreamUpdate({ type: 'error', message: error.message });
      } else {
        handleStreamUpdate({ type: 'error', message: 'An unknown error occurred' });
      }
    }
  };

  const addToHistory = (item: HistoryItem) => {
    setHistory(prev => [...prev, item]);
  };

  const clearHistory = useCallback(() => {
    setHistory([]);
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // Memoize history length for performance
  const historyLength = useMemo(() => history.length, [history]);

  return {
    history,
    isLoading,
    error,
    addToHistory,
    clearHistory,
    clearError,
    sendStreamingRequest,
    setIsLoading,
    historyLength
  };
}; 