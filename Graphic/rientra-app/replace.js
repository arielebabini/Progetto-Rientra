const fs = require('fs');
let content = fs.readFileSync('src/components/JobAnalysisView.tsx', 'utf8');

const search = [
  '                        <td className="ja-td-skill" style={{ color: col }}>',
  '                          <span className="ja-skill-name">{s.id.replace(/_/g, \\' \\')}</span>',
  '                          {hasDesc && (',
  '                            <span className={`ja-desc-toggle${isExpanded ? \\' open\\' : \\'\\'}`}>{isExpanded ? \\'▲\\' : \\'▼\\'}</span>',
  '                          )}',
  '                        </td>'
].join('\\r\\n');

const searchLF = search.replace(/\\r\\n/g, '\\n');

const replace = [
  '                        <td className="ja-td-skill" style={{ color: col }}>',
  '                          <div className="ja-skill-name-cell">',
  '                            {hasDesc && (',
  '                              <span className={`ja-row-expander-arrow${isExpanded ? \\' is-expanded\\' : \\'\\'}`} aria-hidden="true">',
  '                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">',
  '                                  <polyline points="6 9 12 15 18 9"></polyline>',
  '                                </svg>',
  '                              </span>',
  '                            )}',
  '                            <span className="ja-skill-name">{s.id.replace(/_/g, \\' \\')}</span>',
  '                          </div>',
  '                        </td>'
].join('\\r\\n');

const replaceLF = replace.replace(/\\r\\n/g, '\\n');

if (content.includes(search)) {
  fs.writeFileSync('src/components/JobAnalysisView.tsx', content.replace(search, replace));
  console.log('Replaced with CRLF');
} else if (content.includes(searchLF)) {
  fs.writeFileSync('src/components/JobAnalysisView.tsx', content.replace(searchLF, replaceLF));
  console.log('Replaced with LF');
} else {
  console.log('Not found in file. Here is the block from the file:');
  const match = content.match(/<td className="ja-td-skill" style=\{\{ color: col \}\}>[\s\S]*?<\/td>/);
  if (match) {
    console.log(match[0]);
  } else {
    console.log('Could not find ANY td with ja-td-skill');
  }
}
