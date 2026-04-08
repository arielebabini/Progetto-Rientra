import { useState, useEffect, useMemo } from 'react';
import './HealthConditionWizard.css';
import {
  fetchAllIcfCodes,
  updateHealthConditions,
  type HealthCondition,
  type IcfCodeEntry,
  type HcChangeItem
} from '../api/semanticService';

type Step = 'select' | 'review' | 'saving' | 'done';

interface HealthConditionWizardProps {
  workerId: string;
  workerDisplayName: string;
  currentConditions: HealthCondition[];
  onClose: () => void;
  onSaved: () => void;
}

const CheckIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12"></polyline>
  </svg>
);

const CloseIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="6" x2="6" y2="18"></line>
    <line x1="6" y1="6" x2="18" y2="18"></line>
  </svg>
);

export default function HealthConditionWizard({ workerId, workerDisplayName, currentConditions, onClose, onSaved }: HealthConditionWizardProps) {
  const [step, setStep] = useState<Step>('select');
  const [allIcfCodes, setAllIcfCodes] = useState<IcfCodeEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState('');
  
  // Set of icf_codes that are checked (including currently assigned + newly selected)
  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set());
  
  // Map of icf_code -> new qualifier assigned in Step 2. Defaulting to 1.
  const [assignedQualifiers, setAssignedQualifiers] = useState<Record<string, number>>({});

  useEffect(() => {
    // initialize selectedCodes with worker's current conditions
    const current = new Set(currentConditions.map(c => c.icf_code));
    setSelectedCodes(current);
    
    // initialize qualifiers
    const initialQuals: Record<string, number> = {};
    currentConditions.forEach(c => {
      // Fallback logic, we're editing BF Qualifier mostly
      const q = c.bf_qualifier ?? c.ap1_qualifier ?? null;
      if (q !== null) initialQuals[c.icf_code] = q;
    });
    setAssignedQualifiers(initialQuals);

    fetchAllIcfCodes()
      .then(codes => {
        setAllIcfCodes(codes);
        setError(null);
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [currentConditions]);

  const filteredCodes = useMemo(() => {
    const q = search.toLowerCase();
    return allIcfCodes.filter(c => 
      c.icf_code.toLowerCase().includes(q) || 
      c.icf_name.toLowerCase().includes(q)
    );
  }, [allIcfCodes, search]);

  const toggleSelection = (code: string) => {
    const next = new Set(selectedCodes);
    if (next.has(code)) {
      next.delete(code);
    } else {
      next.add(code);
      // assign default qualifier 1 to new code
      setAssignedQualifiers(prev => ({ ...prev, [code]: 1 }));
    }
    setSelectedCodes(next);
  };

  const handleQualifierSelect = (code: string, q: number) => {
    setAssignedQualifiers(prev => ({ ...prev, [code]: q }));
  };

  const handleConfirm = async () => {
    if (step === 'select') {
      setStep('review');
      return;
    }

    if (step === 'review') {
      setStep('saving');
      setError(null);

      // Build changes payload
      const currentMap = new Map(currentConditions.map(c => [c.icf_code, c]));
      const changes: HcChangeItem[] = [];

      // Find removals (was in current, but not in selected)
      for (const c of currentConditions) {
        if (!selectedCodes.has(c.icf_code)) {
          changes.push({ icf_code: c.icf_code, action: 'remove', qualifier: null });
        }
      }

      // Find adds and modifies (in selected)
      for (const code of Array.from(selectedCodes)) {
        const isNew = !currentMap.has(code);
        const oldQual = currentMap.get(code)?.bf_qualifier ?? currentMap.get(code)?.ap1_qualifier ?? null;
        const newQual = assignedQualifiers[code] ?? 1;

        if (isNew) {
          changes.push({ icf_code: code, action: 'add', qualifier: newQual });
        } else if (oldQual !== newQual) {
          changes.push({ icf_code: code, action: 'modify', qualifier: newQual });
        }
      }

      if (changes.length === 0) {
        // Nothing to do
        onSaved();
        onClose();
        return;
      }

      try {
        await updateHealthConditions(workerId, changes);
        setStep('done');
        setTimeout(() => {
          onSaved();
          onClose();
        }, 800);
      } catch (err: any) {
        setError(err.message || 'Failed to save changes.');
        setStep('review');
      }
    }
  };

  // Groups for review step
  const currentSet = useMemo(() => new Set(currentConditions.map(c => c.icf_code)), [currentConditions]);
  const toModify = allIcfCodes.filter(c => currentSet.has(c.icf_code) && selectedCodes.has(c.icf_code));
  const toAdd = allIcfCodes.filter(c => !currentSet.has(c.icf_code) && selectedCodes.has(c.icf_code));
  const toRemove = currentConditions.filter(c => !selectedCodes.has(c.icf_code));


  return (
    <div className="hc-wizard-overlay">
      <div className="hc-wizard-modal">
        {/* Header */}
        <div className="hc-wizard-header">
          <div>
            <h2 className="hc-wizard-title">{workerDisplayName} / Modify Health Conditions</h2>
            <p className="hc-wizard-subtitle">
              {step === 'select' 
                ? 'Identify the condition regarding the worker by selecting the ICF code describing them'
                : 'Select the qualifier number regarding each ICF code'
              }
            </p>
          </div>
          <button className="hc-wizard-close-btn" onClick={onClose}><CloseIcon /></button>
        </div>

        {/* Content */}
        <div className="hc-wizard-content">
          {error && (
            <div className="hc-wizard-error">
              ⚠ {error}
            </div>
          )}

          {step === 'select' && (
            <>
              <div className="hc-wizard-search-bar">
                <input 
                  type="text" 
                  placeholder="Search..." 
                  value={search} 
                  onChange={e => setSearch(e.target.value)}
                />
              </div>

              <div className="hc-wizard-table-container">
                {loading ? (
                  <div className="hc-wizard-loading">Loading ICF codes...</div>
                ) : (
                  <table className="hc-wizard-table">
                    <thead>
                      <tr>
                        <th style={{ width: 60 }}><CheckIcon /></th>
                        <th style={{ width: 140 }}>ICF Code No.</th>
                        <th>ICF Code Name</th>
                        <th>ICF Category</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredCodes.map(c => {
                        const isChecked = selectedCodes.has(c.icf_code);
                        return (
                          <tr 
                            key={c.icf_code} 
                            onClick={() => toggleSelection(c.icf_code)}
                            className={isChecked ? 'selected-row' : ''}
                          >
                            <td>
                              <div className={`hc-checkbox ${isChecked ? 'checked' : ''}`}>
                                {isChecked && <CheckIcon />}
                              </div>
                            </td>
                            <td className="hc-table-code">{c.icf_code}</td>
                            <td>{c.icf_name || '—'}</td>
                            <td className="hc-table-category">{c.category}</td>
                          </tr>
                        );
                      })}
                      {filteredCodes.length === 0 && (
                        <tr><td colSpan={4} className="hc-table-empty">No codes found</td></tr>
                      )}
                    </tbody>
                  </table>
                )}
              </div>
            </>
          )}

          {step === 'review' && (
            <div className="hc-wizard-review-container">
              <div className="hc-review-table-header">
                <div className="col-code">ICF Code No.</div>
                <div className="col-name">ICF Code Name</div>
                <div className="col-status">Status</div>
                <div className="col-qualifier">Qualifier</div>
                <div className="col-prev">Previous qualifier</div>
              </div>

              {toModify.length > 0 && (
                <div className="hc-review-group">
                  <h4 className="hc-group-title">Codes to be modified</h4>
                  {toModify.map(c => {
                    const prevQ = currentConditions.find(x => x.icf_code === c.icf_code)?.bf_qualifier ?? '-';
                    return (
                      <div className="hc-review-row" key={c.icf_code}>
                        <div className="col-code hc-table-code">{c.icf_code}</div>
                        <div className="col-name">{c.icf_name}</div>
                        <div className="col-status"><span className="hc-status-badge hc-badge-modify">Modify</span></div>
                        <div className="col-qualifier">
                          <QualifierSelector 
                            val={assignedQualifiers[c.icf_code] ?? 1} 
                            onChange={(q) => handleQualifierSelect(c.icf_code, q)} 
                          />
                        </div>
                        <div className="col-prev">{prevQ}</div>
                      </div>
                    );
                  })}
                </div>
              )}

              {toAdd.length > 0 && (
                <div className="hc-review-group">
                  <h4 className="hc-group-title">New added codes</h4>
                  {toAdd.map(c => (
                    <div className="hc-review-row" key={c.icf_code}>
                      <div className="col-code hc-table-code">{c.icf_code}</div>
                      <div className="col-name">{c.icf_name}</div>
                      <div className="col-status"><span className="hc-status-badge hc-badge-add">New addition</span></div>
                      <div className="col-qualifier">
                        <QualifierSelector 
                          val={assignedQualifiers[c.icf_code] ?? 1} 
                          onChange={(q) => handleQualifierSelect(c.icf_code, q)} 
                        />
                      </div>
                      <div className="col-prev">—</div>
                    </div>
                  ))}
                </div>
              )}

              {toRemove.length > 0 && (
                <div className="hc-review-group">
                  <h4 className="hc-group-title">Codes to be removed</h4>
                  {toRemove.map(c => (
                    <div className="hc-review-row hc-row-dimmed" key={c.icf_code}>
                      <div className="col-code hc-table-code">{c.icf_code}</div>
                      <div className="col-name">{c.icf_name}</div>
                      <div className="col-status"><span className="hc-status-badge hc-badge-remove">For removal</span></div>
                      <div className="col-qualifier">—</div>
                      <div className="col-prev">{c.bf_qualifier ?? c.ap1_qualifier ?? '-'}</div>
                    </div>
                  ))}
                </div>
              )}

              {toModify.length === 0 && toAdd.length === 0 && toRemove.length === 0 && (
                 <div className="hc-review-empty">No changes made.</div>
              )}
            </div>
          )}

          {(step === 'saving' || step === 'done') && (
            <div className="hc-wizard-saving">
              {step === 'saving' ? (
                <>
                  <div className="hc-spinner" />
                  <p>Saving modifications...</p>
                </>
              ) : (
                <>
                  <div className="hc-success-icon"><CheckIcon /></div>
                  <p>Changes saved successfully!</p>
                </>
              )}
            </div>
          )}

        </div>

        {/* Footer */}
        {step !== 'saving' && step !== 'done' && (
          <div className="hc-wizard-footer">
            {step === 'select' ? (
              <div className="hc-footer-left">
                {selectedCodes.size} items selected
              </div>
            ) : (
              <div className="hc-footer-left">
                <button className="hc-btn-secondary" onClick={() => setStep('select')}>Back</button>
              </div>
            )}
            <div className="hc-footer-right">
              <button 
                className="hc-btn-primary" 
                onClick={handleConfirm}
                disabled={loading || (step === 'select' && selectedCodes.size === 0)}
              >
                {step === 'select' ? 'Next' : 'Confirm'}
              </button>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

// Inline helper for the 1-4 toggle buttons
function QualifierSelector({ val, onChange }: { val: number, onChange: (v: number) => void }) {
  return (
    <div className="hc-qualifier-group">
      {[1, 2, 3, 4].map(q => (
        <button 
          key={q} 
          className={`hc-qualifier-btn ${val === q ? 'active' : ''}`}
          onClick={() => onChange(q)}
        >
          {q}
        </button>
      ))}
    </div>
  );
}
