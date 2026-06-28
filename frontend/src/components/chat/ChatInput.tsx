import { useState, useCallback, useRef, useEffect } from 'react';

import { useAppStore } from '../../store/appStore';
import { useAgentCall } from '../../hooks/useSSEStream';

export default function ChatInput() {
  const [text, setText] = useState('');
  const { isStreaming, selectedAgent, setSelectedAgent, abort } = useAppStore();
  const { callAgent } = useAgentCall();
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const [isListening, setIsListening] = useState(false);
  const [recognitionSupported, setRecognitionSupported] = useState(false);
  const recognitionRef = useRef<any>(null);

  useEffect(() => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (SpeechRecognition) {
      setRecognitionSupported(true);
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = 'en-IN';

      recognition.onstart = () => setIsListening(true);
      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        if (transcript) {
          setText((prev) => (prev ? `${prev} ${transcript}` : transcript));
        }
      };
      recognition.onerror = (event: any) => {
        console.error('Speech recognition error:', event.error);
        setIsListening(false);
      };
      recognition.onend = () => setIsListening(false);

      recognitionRef.current = recognition;
    }
  }, []);

  const toggleListening = useCallback(() => {
    if (!recognitionRef.current) return;
    if (isListening) {
      recognitionRef.current.stop();
    } else {
      recognitionRef.current.start();
    }
  }, [isListening]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`;
    }
  }, [text]);

  const handleSuggestion = useCallback((agent: 'portfolio' | 'pnl' | 'dividend' | 'stock_analysis') => {
    if (isStreaming) return;
    setSelectedAgent(agent);
    setTimeout(() => {
      callAgent();
      setTimeout(() => setSelectedAgent('auto'), 500);
    }, 50);
  }, [isStreaming, setSelectedAgent, callAgent]);

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed && selectedAgent === 'auto') return;

    if (selectedAgent === 'auto' && trimmed) {
      callAgent(trimmed);
    } else {
      callAgent(trimmed || undefined);
    }
    setText('');
  }, [text, selectedAgent, callAgent]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  return (
    <div className="shrink-0 border-t border-border bg-surface p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2 xl:hidden">
        <span className="select-none pr-1 text-[9px] font-bold uppercase tracking-wider text-muted">
          Quick Analysis:
        </span>
        <button
          onClick={() => handleSuggestion('portfolio')}
          disabled={isStreaming}
          className="rounded-full border border-border bg-canvas px-3 py-1 text-[11px] font-medium text-muted transition-all hover:border-gold/30 hover:text-gold disabled:opacity-50"
        >
          Portfolio Agent
        </button>
        <button
          onClick={() => handleSuggestion('pnl')}
          disabled={isStreaming}
          className="rounded-full border border-border bg-canvas px-3 py-1 text-[11px] font-medium text-muted transition-all hover:border-gold/30 hover:text-gold disabled:opacity-50"
        >
          P&amp;L Agent
        </button>
        <button
          onClick={() => handleSuggestion('dividend')}
          disabled={isStreaming}
          className="rounded-full border border-border bg-canvas px-3 py-1 text-[11px] font-medium text-muted transition-all hover:border-gold/30 hover:text-gold disabled:opacity-50"
        >
          Dividend Agent
        </button>
        <button
          onClick={() => handleSuggestion('stock_analysis')}
          disabled={isStreaming}
          className="rounded-full border border-border bg-canvas px-3 py-1 text-[11px] font-medium text-muted transition-all hover:border-gold/30 hover:text-gold disabled:opacity-50"
        >
          Stock Analysis Agent
        </button>
      </div>

      <div className="flex max-w-full items-end gap-3">
        {recognitionSupported && (
          <button
            onClick={toggleListening}
            disabled={isStreaming}
            className={`flex items-center justify-center self-end rounded-xl border p-3.5 transition-all active:scale-[0.95] ${
              isListening
                ? 'animate-pulse border-rose-500 bg-rose-500/20 text-rose-500'
                : 'border-border bg-canvas text-muted hover:border-gold/30 hover:text-text'
            } disabled:opacity-50`}
            title={isListening ? 'Listening... Click to stop' : 'Use voice input'}
            aria-label="Voice input"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
              <path d="M19 10v1a7 7 0 0 1-14 0v-1" />
              <line x1="12" x2="12" y1="19" y2="22" />
            </svg>
          </button>
        )}

        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isStreaming}
          placeholder={selectedAgent === 'auto' ? 'Ask about your portfolio...' : `Run ${selectedAgent} analysis...`}
          rows={1}
          className="flex-1 resize-none rounded-xl border border-border bg-canvas px-4 py-3 text-sm text-text placeholder-muted/60 transition-colors focus:border-gold focus:outline-none disabled:opacity-50"
          aria-label="Chat input"
        />

        {isStreaming ? (
          <button
            onClick={() => abort?.()}
            className="flex shrink-0 items-center gap-1.5 rounded-xl bg-rose-600 px-4 py-3.5 text-sm font-semibold text-text shadow-lg shadow-rose-950/20 transition-all hover:bg-rose-500 active:scale-[0.97]"
            aria-label="Stop generation"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <rect x="4" y="4" width="16" height="16" rx="2" ry="2" />
            </svg>
            Stop
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!text.trim() && selectedAgent === 'auto'}
            className="shrink-0 rounded-xl bg-gold px-4 py-3.5 text-sm font-semibold text-canvas transition-all hover:bg-goldlt active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="Send message"
          >
            Send
          </button>
        )}
      </div>

      {selectedAgent !== 'auto' && (
        <p className="mt-2 px-1 text-[10px] text-muted/60">
          Press Send to run the {selectedAgent} agent directly, even without a typed message.
        </p>
      )}
    </div>
  );
}
