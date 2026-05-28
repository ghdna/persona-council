import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import './Stage2.css';

function formatMemberId(id) {
  if (!id) return '';
  if (id.includes('/')) {
    return id.split('/')[1];
  }
  return id.split('-').map(w => w[0].toUpperCase() + w.slice(1)).join(' ');
}

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

function personaClassFromMemberId(memberId) {
  if (!memberId) return '';
  if (memberId.includes('/')) return '';
  return `persona-${memberId}`;
}

export default function Stage2({ rankings, labelToModel, aggregateRankings }) {
  const [activeTab, setActiveTab] = useState(0);

  if (!rankings || rankings.length === 0) {
    return null;
  }

  const labelToMember = labelToModel;
  const currentRanking = rankings[activeTab];
  // Prefer the backend-provided display version (persona names already substituted in).
  // Fall back to raw ranking text if the backend didn't pre-compute one.
  const displayText = currentRanking.ranking_display || currentRanking.ranking;

  return (
    <div className="stage stage2">
      <h3 className="stage-title">Stage 2: Peer Rankings</h3>

      <h4>Raw Evaluations</h4>
      <p className="stage-description">
        Each council member evaluated the others' responses with identities anonymized as Response A, B, C, etc. Names are shown in <strong>bold</strong> here for readability; the LLMs themselves saw only the labels.
      </p>

      <div className="tabs">
        {rankings.map((rank, index) => (
          <button
            key={index}
            className={`tab ${personaClass(rank.persona)} ${activeTab === index ? 'active' : ''}`}
            onClick={() => setActiveTab(index)}
          >
            {formatMember(rank)}
          </button>
        ))}
      </div>

      <div className="tab-content">
        <div className="ranking-model">
          {formatMember(currentRanking)}
          {currentRanking.persona && (
            <span style={{ marginLeft: '0.5em', opacity: 0.6, fontSize: '0.85em' }}>
              via {currentRanking.model}
            </span>
          )}
        </div>
        <div className="ranking-content markdown-content">
          <ReactMarkdown>{displayText}</ReactMarkdown>
        </div>

        {(currentRanking.parsed_ranking_display || currentRanking.parsed_ranking || []).length > 0 && (
          <div className="parsed-ranking">
            <strong>Extracted Ranking:</strong>
            <ol>
              {(currentRanking.parsed_ranking_display || currentRanking.parsed_ranking || []).map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ol>
          </div>
        )}
      </div>

      {aggregateRankings && aggregateRankings.length > 0 && (
        <div className="aggregate-rankings">
          <h4>Aggregate Rankings (Street Cred)</h4>
          <p className="stage-description">
            Combined results across all peer evaluations (lower score is better):
          </p>
          <div className="aggregate-list">
            {aggregateRankings.map((agg, index) => (
              <div
                key={index}
                className={`aggregate-item ${personaClassFromMemberId(agg.member_id || agg.model)}`}
              >
                <span className="rank-position">#{index + 1}</span>
                <span className="rank-model">
                  {formatMemberId(agg.member_id || agg.model)}
                </span>
                <span className="rank-score">
                  Avg: {agg.average_rank.toFixed(2)}
                </span>
                <span className="rank-count">
                  ({agg.rankings_count} votes)
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
