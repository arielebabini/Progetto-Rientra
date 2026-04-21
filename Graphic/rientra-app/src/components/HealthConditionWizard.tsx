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
  allCoreSets: string[];   // passed in from WorkersPage (already fetched & working)
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

const FilterIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
  </svg>
);

export default function HealthConditionWizard({ workerId, workerDisplayName, currentConditions, allCoreSets, onClose, onSaved }: HealthConditionWizardProps) {
  const [step, setStep] = useState<Step>('select');
  const [allIcfCodes, setAllIcfCodes] = useState<IcfCodeEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState('');
  const [coreSetFilterOpen,      setCoreSetFilterOpen]      = useState(false);
  const [wizardSelectedCoreSets, setWizardSelectedCoreSets] = useState<string[]>([]);
  const [categoryFilterOpen,     setCategoryFilterOpen]     = useState(false);
  const [selectedCategories,     setSelectedCategories]     = useState<string[]>([]);

  // Each category maps a display label to the ICF code first-character prefix.
  // The filter state stores prefixes ('b', 'd', …) — never label strings.
  const CATEGORIES = [
    { label: 'Body Functions',               prefix: 'b' },
    { label: 'Activities and Participation', prefix: 'd' },
  ];
  
  // Set of icf_codes that are checked (including currently assigned + newly selected)
  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set());
  
  // Map of icf_code -> new qualifier assigned in Step 2. Defaulting to null.
  const [assignedQualifiers, setAssignedQualifiers] = useState<Record<string, number | null>>({});

  useEffect(() => {
    // initialize selectedCodes with worker's current conditions
    const current = new Set(currentConditions.map(c => c.icf_code));
    setSelectedCodes(current);
    
    // initialize qualifiers
    const initialQuals: Record<string, number | null> = {};
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

  const normalizedIcfCodes = useMemo(() => {
    const byCode = new Map<string, IcfCodeEntry>();

    allIcfCodes.forEach(code => {
      const existing = byCode.get(code.icf_code);
      if (!existing) {
        byCode.set(code.icf_code, {
          ...code,
          core_sets: [...new Set(code.core_sets || [])],
        });
        return;
      }

      byCode.set(code.icf_code, {
        ...existing,
        icf_name: existing.icf_name || code.icf_name,
        category: existing.category !== 'Other' ? existing.category : code.category,
        core_sets: [...new Set([...(existing.core_sets || []), ...(code.core_sets || [])])],
      });
    });

    return Array.from(byCode.values()).sort((a, b) => a.icf_code.localeCompare(b.icf_code));
  }, [allIcfCodes]);

  // Derive unique core sets from the full catalogue
  const filteredCodes = useMemo(() => {
    const q = search.toLowerCase();
    const matchesText = (c: IcfCodeEntry) =>
      c.icf_code.toLowerCase().includes(q) ||
      c.icf_name.toLowerCase().includes(q) ||
      (c.core_sets || []).join(' ').toLowerCase().includes(q);
    const matchesFilter = (c: IcfCodeEntry) =>
      wizardSelectedCoreSets.length === 0 ||
      (c.core_sets || []).some(cs => wizardSelectedCoreSets.includes(cs));
    // selectedCategories holds ICF prefix chars ('b', 'd', …) — check directly against icf_code.
    const matchesCategory = (c: IcfCodeEntry) =>
      selectedCategories.length === 0 ||
      selectedCategories.includes(c.icf_code.toLowerCase().charAt(0));
    return normalizedIcfCodes.filter(c => matchesText(c) && matchesFilter(c) && matchesCategory(c));
  }, [normalizedIcfCodes, search, wizardSelectedCoreSets, selectedCategories]);

  const toggleSelection = (code: string) => {
    const next = new Set(selectedCodes);
    if (next.has(code)) {
      next.delete(code);
    } else {
      next.add(code);
      // explicit missing qualifier logic
      setAssignedQualifiers(prev => ({ ...prev, [code]: null }));
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
      const hasMissing = Array.from(selectedCodes).some(code => assignedQualifiers[code] == null);
      if (hasMissing) {
        const container = document.querySelector('.hc-wizard-review-container');
        const firstErrorEl = document.querySelector('.hc-row-error');
        if (container && firstErrorEl) {
          const containerRect = container.getBoundingClientRect();
          const elRect = firstErrorEl.getBoundingClientRect();
          const offsetTop = container.scrollTop + (elRect.top - containerRect.top) - (containerRect.height / 2) + (elRect.height / 2);
          container.scrollTo({ top: offsetTop, behavior: 'smooth' });
        }
        return;
      }

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
        const newQual = assignedQualifiers[code] ?? null;

        if (isNew) {
          if (newQual !== null) {
            changes.push({ icf_code: code, action: 'add', qualifier: newQual });
          }
        } else if (oldQual !== newQual && newQual !== null) {
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
  const toModify = normalizedIcfCodes.filter(c => currentSet.has(c.icf_code) && selectedCodes.has(c.icf_code));
  const toAdd = normalizedIcfCodes.filter(c => !currentSet.has(c.icf_code) && selectedCodes.has(c.icf_code));
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
              <div className="hc-wizard-search-bar" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <input
                  type="text"
                  placeholder="Search..."
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  style={{ width: 260, maxWidth: '100%' }}
                />

                {/* Category filter */}
                <div style={{ position: 'relative' }}>
                  <button
                    onClick={(e) => { e.stopPropagation(); setCategoryFilterOpen(v => !v); }}
                    style={{
                      background: categoryFilterOpen || selectedCategories.length > 0
                        ? 'rgba(77,217,192,0.15)' : 'rgba(255,255,255,0.04)',
                      border: `1px solid ${categoryFilterOpen || selectedCategories.length > 0 ? '#4DD9C0' : 'var(--border-color)'}`,
                      borderRadius: 8,
                      color: categoryFilterOpen || selectedCategories.length > 0 ? '#4DD9C0' : 'var(--text-muted)',
                      cursor: 'pointer',
                      fontSize: '0.875rem',
                      fontWeight: 500,
                      transition: 'all 0.2s',
                      whiteSpace: 'nowrap',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: '9px 14px',
                      outline: 'none',
                      fontFamily: 'inherit',
                    }}
                    title="Filter by Category"
                  >
                    <FilterIcon />
                    Category
                    {selectedCategories.length > 0 && (
                      <span style={{
                        background: '#4DD9C0', color: '#0f2233', borderRadius: '99px',
                        fontSize: '0.7rem', fontWeight: 700, padding: '1px 7px',
                      }}>{selectedCategories.length}</span>
                    )}
                  </button>

                  {categoryFilterOpen && (
                    <div style={{
                      position: 'absolute', top: 'calc(100% + 6px)', left: 0, zIndex: 50,
                      minWidth: 240, maxHeight: 320, overflowY: 'auto',
                      background: '#1a2e4a',
                      border: '1px solid rgba(255,255,255,0.12)',
                      borderRadius: 10,
                      boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
                      padding: '6px 0',
                    }}>
                      {/* Header */}
                      <div style={{ padding: '6px 14px 4px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontSize: '0.72rem', fontWeight: 600, color: 'rgba(255,255,255,0.45)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Filter by Category</span>
                        {selectedCategories.length > 0 && (
                          <button
                            onClick={() => setSelectedCategories([])}
                            style={{ background: 'none', border: 'none', color: '#4DD9C0', cursor: 'pointer', fontSize: '0.75rem', padding: 0 }}
                          >Clear all</button>
                        )}
                      </div>
                      <div style={{ height: 1, background: 'rgba(255,255,255,0.08)', margin: '4px 0' }} />

                      {CATEGORIES.map(({ label, prefix }) => {
                        const checked = selectedCategories.includes(prefix);
                        return (
                          <button
                            key={prefix}
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedCategories(prev =>
                                checked ? prev.filter(x => x !== prefix) : [...prev, prefix]
                              );
                            }}
                            style={{
                              display: 'flex', alignItems: 'center',
                              gap: 10, width: '100%', padding: '8px 14px',
                              cursor: 'pointer', transition: 'background 0.15s',
                              fontSize: '0.83rem', color: 'var(--text-base)',
                              boxSizing: 'border-box',
                              background: 'transparent',
                              border: 'none',
                              textAlign: 'left',
                              fontFamily: 'inherit',
                              outline: 'none',
                            }}
                            onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.06)')}
                            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                          >
                            <span style={{
                              width: 16, height: 16, borderRadius: 4, flexShrink: 0,
                              border: `2px solid ${checked ? '#4DD9C0' : 'rgba(255,255,255,0.3)'}`,
                              background: checked ? '#4DD9C0' : 'transparent',
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                              transition: 'all 0.15s',
                              pointerEvents: 'none',
                            }}>
                              {checked && (
                                <svg width="10" height="10" viewBox="0 0 12 12" fill="none">
                                  <polyline points="2 6 5 9 10 3" stroke="#0f2233" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                                </svg>
                              )}
                            </span>
                            {label}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Core Set filter */}
                <div style={{ position: 'relative' }}>
                  <button
                    onClick={(e) => { e.stopPropagation(); setCoreSetFilterOpen(v => !v); }}
                    style={{
                      background: coreSetFilterOpen || wizardSelectedCoreSets.length > 0
                        ? 'rgba(77,217,192,0.15)' : 'rgba(255,255,255,0.04)',
                      border: `1px solid ${coreSetFilterOpen || wizardSelectedCoreSets.length > 0 ? '#4DD9C0' : 'var(--border-color)'}`,
                      borderRadius: 8,
                      color: coreSetFilterOpen || wizardSelectedCoreSets.length > 0 ? '#4DD9C0' : 'var(--text-muted)',
                      cursor: 'pointer',
                      fontSize: '0.875rem',
                      fontWeight: 500,
                      transition: 'all 0.2s',
                      whiteSpace: 'nowrap',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: '9px 14px',
                      outline: 'none',
                      fontFamily: 'inherit',
                    }}
                    title="Filter by Core Set"
                  >
                    <FilterIcon />
                    Core Set
                    {wizardSelectedCoreSets.length > 0 && (
                      <span style={{
                        background: '#4DD9C0', color: '#0f2233', borderRadius: '99px',
                        fontSize: '0.7rem', fontWeight: 700, padding: '1px 7px',
                      }}>{wizardSelectedCoreSets.length}</span>
                    )}
                  </button>

                  {coreSetFilterOpen && (
                    <div style={{
                      position: 'absolute', top: 'calc(100% + 6px)', left: 0, zIndex: 50,
                      minWidth: 260, maxHeight: 320, overflowY: 'auto',
                      background: '#1a2e4a',
                      border: '1px solid rgba(255,255,255,0.12)',
                      borderRadius: 10,
                      boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
                      padding: '6px 0',
                    }}>
                      {/* Header */}
                      <div style={{ padding: '6px 14px 4px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontSize: '0.72rem', fontWeight: 600, color: 'rgba(255,255,255,0.45)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Filter by Core Set</span>
                        {wizardSelectedCoreSets.length > 0 && (
                          <button
                            onClick={() => setWizardSelectedCoreSets([])}
                            style={{ background: 'none', border: 'none', color: '#4DD9C0', cursor: 'pointer', fontSize: '0.75rem', padding: 0 }}
                          >Clear all</button>
                        )}
                      </div>
                      <div style={{ height: 1, background: 'rgba(255,255,255,0.08)', margin: '4px 0' }} />

                      {allCoreSets.length === 0 ? (
                        <div style={{ padding: '10px 14px', color: 'rgba(255,255,255,0.35)', fontSize: '0.82rem' }}>No core sets available</div>
                      ) : (
                        allCoreSets.map(cs => {
                          const checked = wizardSelectedCoreSets.includes(cs);
                          return (
                            <button
                              key={cs}
                              onClick={(e) => {
                                e.stopPropagation();
                                setWizardSelectedCoreSets(prev =>
                                  checked ? prev.filter(x => x !== cs) : [...prev, cs]
                                );
                              }}
                              style={{
                                display: 'flex', alignItems: 'center',
                                gap: 10, width: '100%', padding: '8px 14px',
                                cursor: 'pointer', transition: 'background 0.15s',
                                fontSize: '0.83rem', color: 'var(--text-base)',
                                boxSizing: 'border-box',
                                background: 'transparent',
                                border: 'none',
                                textAlign: 'left',
                                fontFamily: 'inherit',
                                outline: 'none',
                              }}
                              onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.06)')}
                              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                            >
                              <span style={{
                                width: 16, height: 16, borderRadius: 4, flexShrink: 0,
                                border: `2px solid ${checked ? '#4DD9C0' : 'rgba(255,255,255,0.3)'}`,
                                background: checked ? '#4DD9C0' : 'transparent',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                transition: 'all 0.15s',
                                pointerEvents: 'none',
                              }}>
                                {checked && (
                                  <svg width="10" height="10" viewBox="0 0 12 12" fill="none">
                                    <polyline points="2 6 5 9 10 3" stroke="#0f2233" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                                  </svg>
                                )}
                              </span>
                              {cs}
                            </button>
                          );
                        })
                      )}
                    </div>
                  )}
                </div>
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
                        <th>Core Set</th>
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
                            <td className="hc-table-category" style={{ fontSize: '0.75rem', opacity: 0.8 }}>{(c.core_sets || []).join(', ') || '—'}</td>
                          </tr>
                        );
                      })}
                      {filteredCodes.length === 0 && (
                        <tr><td colSpan={5} className="hc-table-empty">No codes found</td></tr>
                      )}
                    </tbody>
                  </table>
                )}
              </div>
            </>
          )}

          {step === 'review' && (
            <div className="hc-wizard-review-container">

              {toModify.length > 0 && (
                <div className="hc-review-group">
                  <h4 className="hc-group-title">Codes to be modified</h4>
                  <ReviewTableHeader />
                  {toModify.map(c => {
                    const prevQ = currentConditions.find(x => x.icf_code === c.icf_code)?.bf_qualifier ?? '-';
                    return (
                      <div className={`hc-review-row ${assignedQualifiers[c.icf_code] == null ? 'hc-row-error' : ''}`} key={c.icf_code}>
                        <div className="col-code hc-table-code">{c.icf_code}</div>
                        <div className="col-name">{c.icf_name}</div>
                        <div className="col-status"><span className="hc-status-badge hc-badge-modify">Modify</span></div>
                        <div className="col-qualifier">
                          <QualifierSelector 
                            val={assignedQualifiers[c.icf_code] ?? null} 
                            onChange={(q) => handleQualifierSelect(c.icf_code, q)} 
                            allowZero={true}
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
                  <ReviewTableHeader />
                  {toAdd.map(c => (
                    <div className={`hc-review-row ${assignedQualifiers[c.icf_code] == null ? 'hc-row-error' : ''}`} key={c.icf_code}>
                      <div className="col-code hc-table-code">{c.icf_code}</div>
                      <div className="col-name">{c.icf_name}</div>
                      <div className="col-status"><span className="hc-status-badge hc-badge-add">New addition</span></div>
                      <div className="col-qualifier">
                        <QualifierSelector 
                          val={assignedQualifiers[c.icf_code] ?? null} 
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
                  <ReviewTableHeader />
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
                disabled={
                  loading || 
                  (step === 'select' && selectedCodes.size === 0)
                }
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

// Inline helper for the 1-4 (or 0-4) toggle buttons
function QualifierSelector({ val, onChange, allowZero }: { val: number | null, onChange: (v: number) => void, allowZero?: boolean }) {
  const options = allowZero ? [0, 1, 2, 3, 4] : [1, 2, 3, 4];
  return (
    <div className="hc-qualifier-group">
      {options.map(q => (
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

function ReviewTableHeader() {
  return (
    <div className="hc-review-table-header">
      <div className="col-code">ICF Code No.</div>
      <div className="col-name">ICF Code Name</div>
      <div className="col-status">Status</div>
      <div className="col-qualifier">Qualifier</div>
      <div className="col-prev">Previous qualifier</div>
    </div>
  );
}
