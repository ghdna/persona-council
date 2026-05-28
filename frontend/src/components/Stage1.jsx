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

export default function Stage1({ responses }) {
  const [activeTab, setActiveTab] = useState(0);

  if (!responses || responses.length === 0) {
    return null;
  }

  return (
    <div className="stage stage1">
      <h3 className="stage-title">Stage 1: Individual Responses</h3>

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
    </div>
  );
}
