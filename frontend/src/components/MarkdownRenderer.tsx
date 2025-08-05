import React, { useEffect, memo } from 'react';
import ReactMarkdown, { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkParse from 'remark-parse';
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

import { TextRenderer } from './markdown/TextRenderer';
import { CodeRenderer } from './markdown/CodeRenderer';
import { 
  TableContainer, 
  TableHeader, 
  TableBody, 
  TableRow, 
  TableHeaderCell, 
  TableCell 
} from './markdown/TableComponents';

interface MarkdownComponentProps {
  children?: React.ReactNode;
  node?: {
    parentNode?: {
      tagName?: string;
    };
  };
  [key: string]: unknown;
}

const MarkdownRendererComponent: React.FC<{ content: string }> = ({ content }) => {
  useEffect(() => {
    // Fonction pour s'assurer que Prism est disponible et que le DOM est rendu
    const highlightCode = () => {
      if (typeof Prism !== 'undefined') {
        Prism.highlightAll();
      }
    };

    // Premier essai immédiat
    highlightCode();
    
    // Essai avec délai pour s'assurer que le DOM est complètement rendu
    const timer1 = setTimeout(highlightCode, 50);
    
    // Essai avec délai plus long pour les cas où le rendu prend plus de temps
    const timer2 = setTimeout(highlightCode, 200);
    
    // Essai avec délai encore plus long pour les cas extrêmes
    const timer3 = setTimeout(highlightCode, 500);
    
    // Utiliser MutationObserver pour détecter quand le DOM est vraiment prêt
    const observer = new MutationObserver((mutations) => {
      // Vérifier si des éléments de code ont été ajoutés
      const hasCodeElements = mutations.some(mutation => 
        Array.from(mutation.addedNodes).some(node => 
          node.nodeType === Node.ELEMENT_NODE && 
          (node as Element).querySelector('pre code, .code-block code')
        )
      );
      
      if (hasCodeElements) {
        highlightCode();
      }
    });
    
    // Observer les changements dans le document
    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
    
    return () => {
      clearTimeout(timer1);
      clearTimeout(timer2);
      clearTimeout(timer3);
      observer.disconnect();
    };
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
      <TableContainer {...props}>{children}</TableContainer>
    ),
    thead: ({ children, ...props }: MarkdownComponentProps) => (
      <TableHeader {...props}>{children}</TableHeader>
    ),
    tbody: ({ children, ...props }: MarkdownComponentProps) => (
      <TableBody {...props}>{children}</TableBody>
    ),
    tr: ({ children, ...props }: MarkdownComponentProps) => (
      <TableRow {...props}>{children}</TableRow>
    ),
    th: ({ children, ...props }: MarkdownComponentProps) => (
      <TableHeaderCell {...props}>{children}</TableHeaderCell>
    ),
    td: ({ children, ...props }: MarkdownComponentProps) => (
      <TableCell {...props}>{children}</TableCell>
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
    code: ({ inline, className, children, ...props }: { inline?: boolean; className?: string; children: React.ReactNode; [key: string]: unknown }) => {
      const childrenString = String(children);
      const hasNewlines = childrenString.includes('\n');
      
      if (className && className.startsWith('language-')) {
        // Bloc de code avec langage spécifié
        return (
          <CodeRenderer inline={inline} className={className} {...props}>
            {children}
          </CodeRenderer>
        );
      } else if (hasNewlines) {
        // Bloc de code sans langage spécifié (avec retours à la ligne)
        return (
          <CodeRenderer inline={false} className="" {...props}>
            {children}
          </CodeRenderer>
        );
      } else {
        // Inline code
        return (
          <code className="inline-code" {...props}>
            {children}
          </code>
        );
      }
    },
  };

  return (
    <ReactMarkdown components={components as Components} remarkPlugins={[remarkParse, remarkGfm]}>
      {content}
    </ReactMarkdown>
  );
};

export const MarkdownRenderer = memo(MarkdownRendererComponent); 