/**
 * @fileoverview Main application component for the terminal-like interface
 * @module App
 */

import { useEffect } from 'react'
import { Terminal } from './components/Terminal'
import { LoginScreen } from './components/LoginScreen'
import { useAuth } from './hooks/useAuth'
import { useStreaming } from './hooks/useStreaming'
import { useTerminal } from './hooks/useTerminal'
import { useTheme } from './hooks/useTheme'

/**
 * Main App component that manages the terminal-like interface
 * @component
 * @returns {JSX.Element} The rendered App component
 */
function App() {
  const { isAuthenticated, user, error: authError, handleLogin, handleLogout } = useAuth();
  const { history, isLoading, error: streamingError, addToHistory, clearHistory, sendStreamingRequest, setIsLoading } = useStreaming();
  const { input, error: terminalError, handleKeyDown, handleChange, handlePaste, handleSubmit, setInput } = useTerminal(
    addToHistory,
    sendStreamingRequest,
    setIsLoading,
    () => {} // setError is handled in useStreaming
  );
  const { theme, toggleTheme } = useTheme();

  useEffect(() => {
    const initializeApp = async () => {
      // Check for error in URL parameters
      const params = new URLSearchParams(window.location.search);
      const errorParam = params.get('error');
      if (errorParam) {
        // Clear error from URL
        window.history.replaceState({}, '', '/');
      }

      // Clear conversation
      clearHistory();
    };

    initializeApp();
  }, [clearHistory]); // clearHistory is now stable with useCallback

  // Configure all links to open in new tab
  useEffect(() => {
    const configureLinks = () => {
      const links = document.querySelectorAll('a[href^="http"]');
      links.forEach(link => {
        if (!link.hasAttribute('target')) {
          link.setAttribute('target', '_blank');
          link.setAttribute('rel', 'noopener noreferrer');
        }
      });
    };

    // Configure existing links
    configureLinks();

    // Set up a mutation observer to handle dynamically added links
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
          if (node.nodeType === Node.ELEMENT_NODE) {
            const element = node as Element;
            const links = element.querySelectorAll ? element.querySelectorAll('a[href^="http"]') : [];
            links.forEach(link => {
              if (!link.hasAttribute('target')) {
                link.setAttribute('target', '_blank');
                link.setAttribute('rel', 'noopener noreferrer');
              }
            });
          }
        });
      });
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true
    });

    return () => observer.disconnect();
  }, []);

  // Handle retry function
  const handleRetry = async (content: string) => {
    setInput(content);
    addToHistory({ type: 'text', content: `>_ ${content}` });
    setIsLoading(true);

    try {
      await sendStreamingRequest(content, undefined);
    } catch {
      // Error handling is done in useStreaming
    } finally {
      setInput('');
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="App">
        <LoginScreen error={authError} onLogin={handleLogin} />
      </div>
    );
  }

  return (
    <div className="App">
      <button
        className="theme-toggle"
        onClick={toggleTheme}
        title={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
      >
        {theme === 'light' ? '🌙' : '☀️'}
      </button>
      <Terminal
        user={user}
        history={history}
        input={input}
        isLoading={isLoading}
        error={streamingError || terminalError}
        onLogout={handleLogout}
        onInputChange={handleChange}
        onKeyDown={handleKeyDown}
        onPaste={handlePaste}
        onSubmit={handleSubmit}
        onRetry={handleRetry}
      />
    </div>
  );
}

export default App