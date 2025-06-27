import React, { useState } from 'react';
import { HistoryItem } from '../types';
import { MarkdownRenderer } from './MarkdownRenderer';

interface HistoryLineProps {
  item: HistoryItem;
  index: number;
  hiddenOutputs: Set<number | string>;
  onToggleOutput: (index: number | string) => void;
  responseItems?: HistoryItem[];
}

export const HistoryLine: React.FC<HistoryLineProps> = ({
  item,
  index,
  hiddenOutputs,
  onToggleOutput,
  responseItems = []
}) => {
  const [isImageExpanded, setIsImageExpanded] = useState(false);
  const [isOutputExpanded, setIsOutputExpanded] = useState(false);
  
  const handleCommandClick = (e: React.MouseEvent, commandId: number | string) => {
    e.stopPropagation();
    onToggleOutput(commandId);
  };

  const handleImageClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsImageExpanded(!isImageExpanded);
  };

  const handleOutputToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsOutputExpanded(!isOutputExpanded);
  };

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

  if (item.content.startsWith('>_')) {
    return (
      <div className="history-line">
        <div 
          className="command-line" 
          onClick={(e) => handleCommandClick(e, index)}
          style={{ cursor: 'pointer' }}
        >
          {item.content}
        </div>
        {/* Only render agent-response if it's not hidden OR has content */} 
        {(!hiddenOutputs.has(index) || responseItems.length > 0) && (
          <div className={`agent-response ${hiddenOutputs.has(index) ? '' : 'hidden'}`}>
            {responseItems.map((responseItem, i) => {
              if (responseItem.type === 'text' && responseItem.content.startsWith('$')) {
                const commandId = `cmd-${index}-${i}`;
                const nextItem = responseItems[i + 1];
                const hasOutput = nextItem && 
                                nextItem.type === 'text' && 
                                !nextItem.content.startsWith('$') && 
                                !nextItem.content.startsWith('>_');

                return (
                  <div key={`system-command-${i}`} className="system-command-group">
                    <div 
                      className="command-line" 
                      onClick={(e) => handleCommandClick(e, commandId)}
                      style={{ cursor: 'pointer' }}
                    >
                      {responseItem.content}
                    </div>
                    {hasOutput && (
                      <div className={`command-output ${!hiddenOutputs.has(commandId) ? 'hidden' : ''}`}>
                        {nextItem.content}
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

              return (
                <div key={`response-${i}`} className="response-item">
                  <MarkdownRenderer content={responseItem.content} />
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  if (item.type === 'progress') {
    const hasOutput = item.output !== undefined && item.output !== null;
    const isToolCommand = item.content.startsWith('$ ') && 
                         (item.toolName === 'aws' || 
                          item.toolName === 'hcloud' || 
                          item.toolName === 'kubectl' || 
                          item.toolName === 'helm' || 
                          item.toolName === 'switch_context' ||
                          item.toolName === 'think');
    
    console.log('HistoryLine progress item:', {
      type: item.type,
      content: item.content,
      toolName: item.toolName,
      status: item.status,
      hasOutput,
      isToolCommand,
      output: item.output,
      outputType: typeof item.output,
      conditions: {
        hasOutput: hasOutput,
        isToolCommand: isToolCommand,
        shouldShowToggle: hasOutput && isToolCommand
      }
    });
    
    const isSimpleStatusMessage = !item.content.startsWith('$ ') && !item.toolName;
    
    return (
      <div className="history-line">
        <div className={`progress-line ${item.status || 'running'} ${isSimpleStatusMessage ? 'status-message' : ''}`}>
          <span className="progress-content">
            {item.toolName === 'think' ? 'hard' : item.content}
          </span>
          {hasOutput && isToolCommand && item.toolName !== 'think' && (
            <button 
              className="output-toggle-btn"
              onClick={handleOutputToggle}
              title={isOutputExpanded ? "Hide output" : "Show output"}
            >
              {isOutputExpanded ? '▼' : '▶'}
            </button>
          )}
        </div>
        {hasOutput && isToolCommand && isOutputExpanded && item.toolName !== 'think' && (
          <div className="tool-output-section">
            <div className="tool-output-header">Output:</div>
            <pre className="tool-output-content">
              {typeof item.output === 'object' ? 
                JSON.stringify(item.output, null, 2) : 
                String(item.output)}
            </pre>
          </div>
        )}
      </div>
    );
  }

  if (item.content.startsWith('$')) {
    const commandId = `sys-${index}`;
    const nextItem = responseItems[0];
    const hasOutput = nextItem && 
                    nextItem.type === 'text' && 
                    !nextItem.content.startsWith('$') && 
                    !nextItem.content.startsWith('>_');

    return (
      <div className="history-line">
        <div 
          className="command-line" 
          onClick={(e) => handleCommandClick(e, commandId)}
          style={{ cursor: 'pointer' }}
        >
          {item.content}
        </div>
        {hasOutput && (
          <div className={`command-output ${!hiddenOutputs.has(commandId) ? 'hidden' : ''}`}>
            {nextItem.content}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="history-line">
      <MarkdownRenderer content={item.content} />
    </div>
  );
}; 
