import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import Stage1 from './Stage1';
import Stage2 from './Stage2';
import Stage3 from './Stage3';
import './ChatInterface.css';

const MODE_OPTIONS = [
  { value: 'persona', label: 'Personas (single LLM, multiple personas)' },
  { value: 'model', label: 'Models (Karpathy original: multiple LLMs)' },
  { value: 'hybrid', label: 'Hybrid (multiple LLMs, one persona each)' },
];

function formatProviderKeys(keys) {
  if (!keys || Object.keys(keys).length === 0) return '';
  const active = Object.entries(keys).filter(([, v]) => v).map(([k]) => k);
  if (active.length === 0) return 'No provider keys configured';
  return `Configured: ${active.join(', ')}`;
}

export default function ChatInterface({
  conversation,
  onSendMessage,
  isLoading,
  mode,
  onModeChange,
  selectedModel,
  onModelChange,
  availableModels,
  providerKeys,
}) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [conversation]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (input.trim() && !isLoading) {
      onSendMessage(input);
      setInput('');
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  if (!conversation) {
    return (
      <div className="chat-interface">
        <div className="empty-state">
          <h2>Welcome to Persona Council</h2>
          <p>Create a new conversation to get started</p>
        </div>
      </div>
    );
  }

  const noKeysConfigured = !availableModels || availableModels.length === 0;
  // Model selector is most meaningful in persona mode (one model for all calls).
  // In model/hybrid modes the council uses configured maps, so we hide the selector.
  const showModelSelector = mode === 'persona';

  return (
    <div className="chat-interface">
      <div className="messages-container">
        {conversation.messages.length === 0 ? (
          <div className="empty-state">
            <h2>Start a conversation</h2>
            <p>Ask a question to consult the Persona Council</p>
          </div>
        ) : (
          conversation.messages.map((msg, index) => (
            <div key={index} className="message-group">
              {msg.role === 'user' ? (
                <div className="user-message">
                  <div className="message-label">You</div>
                  <div className="message-content">
                    <div className="markdown-content">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="assistant-message">
                  <div className="message-label">
                    Persona Council
                    {msg.metadata?.mode && (
                      <span className="mode-badge">{msg.metadata.mode}</span>
                    )}
                    {msg.metadata?.model && (
                      <span className="mode-badge">{msg.metadata.model}</span>
                    )}
                  </div>

                  {msg.loading?.stage1 && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>Running Stage 1: Collecting individual responses...</span>
                    </div>
                  )}
                  {msg.stage1 && <Stage1 responses={msg.stage1} />}

                  {msg.loading?.stage2 && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>Running Stage 2: Peer rankings...</span>
                    </div>
                  )}
                  {msg.stage2 && (
                    <Stage2
                      rankings={msg.stage2}
                      labelToModel={msg.metadata?.label_to_member || msg.metadata?.label_to_model}
                      aggregateRankings={msg.metadata?.aggregate_rankings}
                    />
                  )}

                  {msg.loading?.stage3 && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>Running Stage 3: Final synthesis...</span>
                    </div>
                  )}
                  {msg.stage3 && (
                    <Stage3
                      finalResponse={msg.stage3}
                      labelToMember={msg.metadata?.label_to_member || msg.metadata?.label_to_model}
                    />
                  )}
                </div>
              )}
            </div>
          ))
        )}

        {isLoading && (
          <div className="loading-indicator">
            <div className="spinner"></div>
            <span>Consulting the council...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {conversation.messages.length === 0 && (
        <form className="input-form" onSubmit={handleSubmit}>
          {noKeysConfigured && (
            <div className="provider-warning">
              <strong>No provider API keys configured.</strong> Add at least one of
              <code>ANTHROPIC_API_KEY</code>, <code>OPENAI_API_KEY</code>,
              <code>GOOGLE_API_KEY</code>, or <code>OPENROUTER_API_KEY</code> to your <code>.env</code>
              and restart the backend.
            </div>
          )}

          <div className="mode-selector">
            <label htmlFor="mode-select">Council mode:</label>
            <select
              id="mode-select"
              value={mode}
              onChange={(e) => onModeChange(e.target.value)}
              disabled={isLoading || noKeysConfigured}
            >
              {MODE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {showModelSelector && availableModels && availableModels.length > 0 && (
            <div className="mode-selector">
              <label htmlFor="model-select">Model:</label>
              <select
                id="model-select"
                value={selectedModel || ''}
                onChange={(e) => onModelChange(e.target.value)}
                disabled={isLoading}
              >
                {availableModels.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
              <span className="provider-status">{formatProviderKeys(providerKeys)}</span>
            </div>
          )}

          <div className="input-row">
            <textarea
              className="message-input"
              placeholder="Ask your question... (Shift+Enter for new line, Enter to send)"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isLoading || noKeysConfigured}
              rows={3}
            />
            <button
              type="submit"
              className="send-button"
              disabled={!input.trim() || isLoading || noKeysConfigured}
            >
              Send
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
