import { forwardRef } from 'react';
import { HistoryItem } from '../types';
import { HistoryLine } from './HistoryLine';

interface TerminalContentProps {
  history: HistoryItem[];
  hiddenOutputs: Set<number | string>;
  onToggleOutput: (index: number | string) => void;
  error: string | null;
}

export const TerminalContent = forwardRef<HTMLDivElement, TerminalContentProps>(({
  history,
  hiddenOutputs,
  onToggleOutput,
  error
}, ref) => {
  const getResponseItems = (startIndex: number): HistoryItem[] => {
    const items: HistoryItem[] = [];
    let i = startIndex + 1;
    
    // If the current element is a command (starts with >_)
    if (history[startIndex].type === 'text' && history[startIndex].content.startsWith('>_')) {
      // Check if the command follows an image
      const prevItem = startIndex > 0 ? history[startIndex - 1] : null;
      const isImageCommand = prevItem?.type === 'image';

      // If it's not an image command, collect responses normally
      if (!isImageCommand) {
        while (i < history.length && 
               !(history[i].type === 'text' && history[i].content.startsWith('>_'))) {
          if (history[i].type !== 'image') {
            items.push(history[i]);
          }
          i++;
        }
      }
    }
    // If the current element is an image, include the command and response that follow
    else if (history[startIndex].type === 'image') {
      // Add the command that follows the image
      if (i < history.length && history[i].type === 'text' && history[i].content.startsWith('>_')) {
        i++; // Skip the command
        // Collect the response
        while (i < history.length && 
               !(history[i].type === 'text' && history[i].content.startsWith('>_'))) {
          items.push(history[i]);
          i++;
        }
      }
    }
    
    return items;
  };

  // Keep track of items already displayed
  const displayedItems = new Set<number>();

  return (
    <div className="terminal-content" ref={ref}>
      {history.map((item, index) => {
        // If this element has already been displayed as part of a previous response, skip it
        if (displayedItems.has(index)) {
          return null;
        }

        const responseItems = getResponseItems(index);
        
        // If it's an image, mark the command that follows as already displayed
        if (item.type === 'image' && index + 1 < history.length) {
          displayedItems.add(index + 1);
        }
        
        // Mark all elements of the response as displayed
        responseItems.forEach((_, i) => {
          displayedItems.add(index + i + (item.type === 'image' ? 2 : 1));
        });

        return (
          <div key={index}>
            <HistoryLine
              item={item}
              index={index}
              hiddenOutputs={hiddenOutputs}
              onToggleOutput={onToggleOutput}
              responseItems={responseItems}
            />
          </div>
        );
      })}
      
      {error && <div className="error">{error}</div>}
    </div>
  );
}); 