import React, { useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import Prism from 'prismjs';
import 'prismjs/themes/prism-tomorrow.css';
// Import des langages supplémentaires
import 'prismjs/components/prism-bash';
import 'prismjs/components/prism-javascript';
import 'prismjs/components/prism-typescript';
import 'prismjs/components/prism-python';
import 'prismjs/components/prism-json';
import 'prismjs/components/prism-yaml';
import 'prismjs/components/prism-markdown';
import 'prismjs/components/prism-docker';
import 'prismjs/components/prism-sql';

interface MarkdownComponentProps {
  children?: React.ReactNode;
  [key: string]: any;
}

interface CodeProps extends React.HTMLAttributes<HTMLElement> {
  inline?: boolean;
  className?: string;
  children?: React.ReactNode;
}

const containsCodeBlock = (text: string): boolean => {
  const codePatterns = [
    /```[\s\S]*?```/,
    /\$\s*[\w\-\s]+/,
  ];
  return codePatterns.some(pattern => pattern.test(text));
};

const TextRenderer = ({ children, ...props }: MarkdownComponentProps) => {
  if (typeof children === 'string') {
    const hasCode = containsCodeBlock(children);
    return <div className={hasCode ? "text-block" : "text-line"} {...props}>{children}</div>;
  }

  const childrenArray = React.Children.toArray(children);
  const hasCodeBlock = childrenArray.some(
    child => React.isValidElement(child) && 
    ((child.type === 'code' || 
     (typeof child === 'string' && containsCodeBlock(child))))
  );

  return <div className={hasCodeBlock ? "text-block" : "text-line"} {...props}>{children}</div>;
};

const copyToClipboard = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text);
  } catch (err) {
    console.error('Failed to copy text: ', err);
  }
};

export const MarkdownRenderer: React.FC<{ content: string }> = ({ content }) => {
  useEffect(() => {
    Prism.highlightAll();
  }, [content]);

  const components = {
    h1: ({ children, ...props }: MarkdownComponentProps) => (
      <h1 className="markdown-heading" {...props}>{children}</h1>
    ),
    h2: ({ children, ...props }: MarkdownComponentProps) => (
      <h2 className="markdown-heading" {...props}>{children}</h2>
    ),
    h3: ({ children, ...props }: MarkdownComponentProps) => (
      <h3 className="markdown-heading" {...props}>{children}</h3>
    ),
    ul: ({ children, ...props }: MarkdownComponentProps) => (
      <ul className="markdown-list" {...props}>{children}</ul>
    ),
    li: ({ children, ...props }: MarkdownComponentProps) => (
      <li className="list-item" {...props}>{children}</li>
    ),
    table: ({ children, ...props }: MarkdownComponentProps) => (
      <div className="table-container">
        <table className="markdown-table" {...props}>{children}</table>
      </div>
    ),
    thead: ({ children, ...props }: MarkdownComponentProps) => (
      <thead className="table-header" {...props}>{children}</thead>
    ),
    tbody: ({ children, ...props }: MarkdownComponentProps) => (
      <tbody className="table-body" {...props}>{children}</tbody>
    ),
    tr: ({ children, ...props }: MarkdownComponentProps) => (
      <tr className="table-row" {...props}>{children}</tr>
    ),
    th: ({ children, ...props }: MarkdownComponentProps) => (
      <th className="table-header-cell" {...props}>{children}</th>
    ),
    td: ({ children, ...props }: MarkdownComponentProps) => (
      <td className="table-cell" {...props}>{children}</td>
    ),
    p: ({ children, ...props }: MarkdownComponentProps) => {
      // Si le paragraphe est dans une liste, on ne met pas de wrapper
      if (props.node?.parentNode?.tagName === 'li') {
        return <>{children}</>;
      }
      // Sinon on utilise le TextRenderer normal
      return <TextRenderer {...props}>{children}</TextRenderer>;
    },
    strong: ({ children, ...props }: MarkdownComponentProps) => (
      <strong className="markdown-bold" {...props}>{children}</strong>
    ),
    code: ({ inline, className, children, ...props }: CodeProps) => {
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
          <pre className={`code-block ${language ? `language-${language}` : ''}`}>
            <code className={language ? `language-${language}` : ''} {...props}>
              {children}
            </code>
          </pre>
        </div>
      ) : (
        <pre className="simple-code-block">
          <code {...props}>
            {children}
          </code>
        </pre>
      );
    }
  };

  return (
    <ReactMarkdown components={components} remarkPlugins={[remarkGfm]}>
      {content}
    </ReactMarkdown>
  );
}; 