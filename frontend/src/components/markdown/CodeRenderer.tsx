import React, { memo } from 'react';

interface CodeProps extends React.HTMLAttributes<HTMLElement> {
  inline?: boolean;
  className?: string;
  children?: React.ReactNode;
}

const copyToClipboard = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text);
  } catch (err) {
    console.error('Failed to copy text: ', err);
  }
};

const CodeRendererComponent: React.FC<CodeProps> = ({ inline, className, children, ...props }) => {
  const match = /language-(\w+)/.exec(className || '');
  const language = match ? match[1] : '';
  
  if (inline) {
    return (
      <code className="inline-code" {...props}>
        {children}
      </code>
    );
  }

  if (language) {
    return (
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
        <pre className={`code-block ${language ? `language-${language}` : ''}`}>
          <code className={language ? `language-${language}` : ''} {...props}>
            {children}
          </code>
        </pre>
      </div>
    );
  }

  return (
    <pre className="simple-code-block">
      <code {...props}>
        {children}
      </code>
    </pre>
  );
};

export const CodeRenderer = memo(CodeRendererComponent); 