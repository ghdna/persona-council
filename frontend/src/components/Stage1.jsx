import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import './Stage1.css';

function formatMember(item) {
  if (!item) return '';
  if (item.persona) {
    return item.persona.split('-').map(w => w[0].toUpperCase() + w.slice(1)).join(' ');
  }
  return item.model?.split('/')[1] || item.model || '';
}

function personaClass(persona) {
  return persona ? `persona-${persona}` : '';
}

export default function Stage1({ responses, failures }) {
  const [activeTab, setActiveTab] = useState(0);

  const hasResponses = responses && responses.length > 0;
  const hasFailures = failures && failures.length > 0;
  if (!hasResponses && !hasFailures) {
    return null;
  }

  const total = (responses?.length || 0) + (failures?.length || 0);
  // Failures in persona mode share one model, so show a single representative error.
  const failureError = hasFailures ? failures[0].error : null;

  return (
    <div className="stage stage1">
      <h3 className="stage-title">Stage 1: Individual Responses</h3>

      {hasFailures && (
        <div className="stage1-failures">
          <strong>
            ⚠ {failures.length} of {total} member{total === 1 ? '' : 's'} didn't respond
            {hasResponses ? ' and were skipped' : ''}:
          </strong>{' '}
          {failures.map(formatMember).filter(Boolean).join(', ')}
          {failureError ? ` — ${failureError}` : ''}.
          <div className="stage1-failures-hint">
            Local Ollama models (especially slow reasoning models) can time out when the
            council runs members in parallel. See the README's “Ollama known issues”.
          </div>
        </div>
      )}

      {hasResponses && (
      <>
      <div className="tabs">
        {responses.map((resp, index) => (
          <button
            key={index}
            className={`tab ${personaClass(resp.persona)} ${activeTab === index ? 'active' : ''}`}
            onClick={() => setActiveTab(index)}
          >
            {formatMember(resp)}
          </button>
        ))}
      </div>

      <div className="tab-content">
        <div className="model-name">
          {formatMember(responses[activeTab])}
          {responses[activeTab].persona && (
            <span style={{ marginLeft: '0.5em', opacity: 0.6, fontSize: '0.85em' }}>
              via {responses[activeTab].model}
            </span>
          )}
        </div>
        <div className="response-text markdown-content">
          <ReactMarkdown>{responses[activeTab].response}</ReactMarkdown>
        </div>
      </div>
      </>
      )}
    </div>
  );
}
