import ReactMarkdown from 'react-markdown';
import './Stage3.css';

function formatModel(model) {
  if (!model) return '';
  if (model.includes('/')) {
    return model.split('/')[1];
  }
  return model;
}

function formatMemberId(id) {
  if (!id) return '';
  if (id.includes('/')) return id.split('/')[1];
  return id.split('-').map(w => w[0].toUpperCase() + w.slice(1)).join(' ');
}

// Safety net: if any "Response X" labels leak through the backend, rewrite them
// to persona names for display.
function deAnonymizeText(text, labelToMember) {
  if (!labelToMember || !text) return text;
  let result = text;
  Object.entries(labelToMember).forEach(([label, memberId]) => {
    const displayName = formatMemberId(memberId);
    result = result.replace(new RegExp(label, 'g'), `**${displayName}**`);
  });
  return result;
}

export default function Stage3({ finalResponse, labelToMember }) {
  if (!finalResponse) {
    return null;
  }

  return (
    <div className="stage stage3">
      <h3 className="stage-title">Stage 3: Final Council Answer</h3>
      <div className="final-response">
        <div className="chairman-label">
          Chairman: {formatModel(finalResponse.model)}
        </div>
        <div className="final-text markdown-content">
          <ReactMarkdown>
            {deAnonymizeText(finalResponse.response, labelToMember)}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
