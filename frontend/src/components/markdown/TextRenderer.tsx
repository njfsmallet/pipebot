import React, { memo } from 'react';

interface MarkdownComponentProps {
  children?: React.ReactNode;
  node?: {
    parentNode?: {
      tagName?: string;
    };
  };
  [key: string]: unknown;
}

const containsCodeBlock = (text: string): boolean => {
  const codePatterns = [
    /```[\s\S]*?```/,
    /\$\s*[\w\-\s]+/,
  ];
  return codePatterns.some(pattern => pattern.test(text));
};

const TextRendererComponent: React.FC<MarkdownComponentProps> = ({ children, ...props }) => {
  const childrenArray = React.Children.toArray(children);
  const hasCodeBlock = childrenArray.some(
    child => React.isValidElement(child) && 
    ((child.type === 'code' || 
     (typeof child === 'string' && containsCodeBlock(child))))
  );

  const isKubectlCommand = childrenArray.some(
    child => typeof child === 'string' && child.trim().startsWith('$ kubectl')
  );
  
  const baseClassName = hasCodeBlock ? "text-block" : "text-line";
  const className = isKubectlCommand ? `${baseClassName} kubectl-command` : baseClassName;
  return <div className={className} {...props}>{children}</div>;
};

export const TextRenderer = memo(TextRendererComponent); 