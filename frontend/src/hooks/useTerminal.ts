import { useState, useRef, useEffect } from 'react';
import { KeyboardEvent } from 'react';
import { HistoryItem } from '../types';

export const useTerminal = (addToHistory: (item: HistoryItem) => void, sendStreamingRequest: (command: string, image?: { base64Data: string; type: string }) => Promise<void>, setIsLoading: (loading: boolean) => void, setError: (error: string | null) => void) => {
  const [input, setInput] = useState<string>('');
  const [textareaHeight, setTextareaHeight] = useState<number>(0);
  const [error, setLocalError] = useState<string | null>(null);
  const terminalRef = useRef<HTMLDivElement>(null);
  const initializedRef = useRef<boolean>(false);

  /**
   * Adjusts textarea height based on content
   */
  const adjustTextareaHeight = (textarea: HTMLTextAreaElement) => {
    // Store current cursor position and selection
    const cursorPosition = textarea.selectionStart;
    const selectionEnd = textarea.selectionEnd;
    
    // Always set height to match content with no maximum height
    textarea.style.height = 'auto';
    textarea.style.height = `${textarea.scrollHeight}px`;
    
    // Remove any scrollable class since we want it to expand naturally
    textarea.classList.remove('scrollable');
    
    // Ensure terminal container scrolls to show the bottom of the textarea
    if (terminalRef.current) {
      // Calculate if cursor is near the bottom
      const isNearBottom = textarea.value.length - cursorPosition < 100;
      
      // Only auto-scroll if cursor is near the bottom
      if (isNearBottom) {
        terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
      }
    }
    
    // Restore cursor position and selection
    requestAnimationFrame(() => {
      textarea.selectionStart = cursorPosition;
      textarea.selectionEnd = selectionEnd;
    });
  };

  /**
   * Effect hook to scroll terminal to bottom when needed
   */
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [textareaHeight]); // Re-scroll when textarea height changes
  
  // Track last cursor position to prevent unwanted scroll jumps
  const lastCursorPosRef = useRef<number>(0);
  
  // Set up initial textarea height and manage scrolling behavior
  useEffect(() => {
    // Find textarea element once the component is mounted
    const textarea = document.querySelector('.input-line') as HTMLTextAreaElement;
    if (textarea) {
      // Set initial height
      adjustTextareaHeight(textarea);
      
      // Track cursor position changes to determine if auto-scrolling should happen
      const handleSelectionChange = () => {
        if (document.activeElement === textarea) {
          const currentPos = textarea.selectionStart;
          lastCursorPosRef.current = currentPos;
        }
      };
      
      // Create resize observer to handle height changes
      const resizeObserver = new ResizeObserver(() => {
        if (terminalRef.current && document.activeElement === textarea) {
          // Only auto-scroll if the cursor is near the bottom of the content
          const isNearBottom = textarea.value.length - lastCursorPosRef.current < 100;
          if (isNearBottom) {
            terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
          }
        }
      });
      
      // Set up event listeners
      textarea.addEventListener('select', handleSelectionChange);
      textarea.addEventListener('click', handleSelectionChange);
      textarea.addEventListener('keyup', handleSelectionChange);
      
      resizeObserver.observe(textarea);
      
      // Clean up observer and event listeners on unmount
      return () => {
        resizeObserver.disconnect();
        textarea.removeEventListener('select', handleSelectionChange);
        textarea.removeEventListener('click', handleSelectionChange);
        textarea.removeEventListener('keyup', handleSelectionChange);
      };
    }
  }, []);

  /**
   * Handles keyboard events in the input textarea
   */
  const handleKeyDown = async (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Handle tab key for indentation
    if (e.key === 'Tab') {
      e.preventDefault();
      const textarea = e.currentTarget;
      const cursorPosition = textarea.selectionStart;
      const newValue = input.slice(0, cursorPosition) + '  ' + input.slice(cursorPosition);
      
      setInput(newValue);
      requestAnimationFrame(() => {
        textarea.selectionStart = cursorPosition + 2;
        textarea.selectionEnd = cursorPosition + 2;
      });
      return;
    }
    
    if (e.key === 'Enter') {
      // Handle Shift+Enter for new lines
      if (e.shiftKey) {
        e.preventDefault();
        const textarea = e.currentTarget;
        const cursorPosition = textarea.selectionStart;
        
        // Store the current scroll position
        const currentScroll = terminalRef.current ? terminalRef.current.scrollTop : 0;
        
        // Add indentation if at the beginning of a line
        let indentation = '';
        if (cursorPosition > 0) {
          // Find start of line
          const lineStart = input.lastIndexOf('\n', cursorPosition - 1) + 1;
          const currentLine = input.slice(lineStart, cursorPosition);
          // Extract leading whitespace from current line
          const match = currentLine.match(/^(\s+)/);
          if (match) {
            indentation = match[1];
          }
        }
        
        const newValue = input.slice(0, cursorPosition) + '\n' + indentation + input.slice(cursorPosition);
        setInput(newValue);
        
        // Update the lastCursorPosRef to the new position after the newline
        const newPosition = cursorPosition + 1 + indentation.length;
        lastCursorPosRef.current = newPosition;
        
        requestAnimationFrame(() => {
          adjustTextareaHeight(textarea);
          
          // Set the cursor position
          textarea.selectionStart = newPosition;
          textarea.selectionEnd = newPosition;
          
          // Update stored height for potential re-renders
          setTextareaHeight(textarea.scrollHeight);
          
          // Ensure cursor visibility - only scroll if near the end
          const isNearEnd = newValue.length - newPosition < 100;
          
          if (isNearEnd && terminalRef.current) {
            terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
          } else if (terminalRef.current) {
            // Keep scroll position relatively stable otherwise
            terminalRef.current.scrollTop = currentScroll;
          }
        });
        return;
      }

      e.preventDefault();
      const command = input.trim();
      if (!command) return;
      
      addToHistory({ type: 'text', content: `>_ ${command}` });
      setIsLoading(true);
      setError(null);
      
      try {
        await sendStreamingRequest(command, undefined);
      } catch {
        setError('Error processing your request. Please check if the backend server is running.');
        setIsLoading(false);
      } finally {
        setInput('');
      }
    }
  };

  /**
   * Handles changes in the input textarea
   */
  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    // Store the current cursor position before making changes
    const cursorPosition = e.target.selectionStart;
    const selectionEnd = e.target.selectionEnd;
    
    // Calculate if we're near the end of the content
    const isNearEnd = e.target.value.length - Math.max(cursorPosition, selectionEnd) < 10;
    
    // Update the input state
    setInput(e.target.value);
    
    // Always adjust textarea height when content changes
    requestAnimationFrame(() => {
      // Update the textarea height
      adjustTextareaHeight(e.target);
      
      // Update stored height for potential re-renders
      setTextareaHeight(e.target.scrollHeight);
      
      // If we were near the end of the content before the change, make sure we scroll to bottom
      if (isNearEnd && terminalRef.current) {
        terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
      }
      
      // Update the lastCursorPosRef
      if (document.activeElement === e.target) {
        lastCursorPosRef.current = e.target.selectionStart;
      }
    });
  };

  /**
   * Handles paste events in the input textarea
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

              addToHistory({
                type: 'image',
                content: imageDescription,
                imageData: base64Image
              });
              addToHistory({ 
                type: 'text', 
                content: `>_ ${imageDescription}` 
              });

              try {
                await sendStreamingRequest(imageDescription, { base64Data, type: file.type });
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

  return {
    input,
    error,
    terminalRef,
    initializedRef,
    textareaHeight,
    handleKeyDown,
    handleChange,
    handlePaste,
    setInput,
    setError: setLocalError
  };
}; 