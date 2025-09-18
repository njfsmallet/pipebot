import { useState, useEffect } from 'react';
import { KeyboardEvent } from 'react';
import { HistoryItem } from '../types';

export const useTerminal = (addToHistory: (item: HistoryItem) => void, sendStreamingRequest: (command: string, image?: { base64Data: string; type: string }) => Promise<void>, setIsLoading: (loading: boolean) => void, setError: (error: string | null) => void) => {
  const [input, setInput] = useState<string>('');
  const [textareaHeight, setTextareaHeight] = useState<number>(0);
  const [error, setLocalError] = useState<string | null>(null);

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

    // Restore cursor position and selection
    requestAnimationFrame(() => {
      textarea.selectionStart = cursorPosition;
      textarea.selectionEnd = selectionEnd;
    });
  };

  // Set up initial textarea height
  useEffect(() => {
    const textarea = document.querySelector('.input-line') as HTMLTextAreaElement;
    if (textarea) {
      adjustTextareaHeight(textarea);
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

        const newPosition = cursorPosition + 1 + indentation.length;

        requestAnimationFrame(() => {
          adjustTextareaHeight(textarea);
          textarea.selectionStart = newPosition;
          textarea.selectionEnd = newPosition;
          setTextareaHeight(textarea.scrollHeight);
        });
        return;
      }

      e.preventDefault();
      const command = input.trim();
      if (!command) return;
      
      addToHistory({ type: 'user-message', content: command });
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
    setInput(e.target.value);

    // Always adjust textarea height when content changes
    // Remove outer requestAnimationFrame to reduce cursor lag
    adjustTextareaHeight(e.target);
    setTextareaHeight(e.target.scrollHeight);
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
                type: 'user-message',
                content: imageDescription
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

  const handleSubmit = async () => {
    const command = input.trim();
    if (!command) return;

    addToHistory({ type: 'user-message', content: command });
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
  };

  return {
    input,
    error,
    textareaHeight,
    handleKeyDown,
    handleChange,
    handlePaste,
    handleSubmit,
    setInput,
    setError: setLocalError
  };
}; 