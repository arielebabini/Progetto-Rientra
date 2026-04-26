import { useState, useEffect, useMemo, useRef, type ReactNode } from 'react';
import './HealthConditionWizard.css';
import {
  fetchAllIcfCodes,
  updateHealthConditions,
  type HealthCondition,
  type IcfCodeEntry,
  type HcChangeItem
} from '../api/semanticService';

type Step = 'select' | 'review' | 'saving' | 'done';

type ParsedDescription = {
  main: string;
  inclusion: string;
  exclusion: string;
};

interface HealthConditionWizardProps {
  workerId: string;
  currentConditions: HealthCondition[];
  allCoreSets: string[];   // passed in from WorkersPage (already fetched & working)
  onClose: () => void;
  onSaved: () => void;
  onStepChange?: (step: Step) => void;
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

const ChevronDownIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="6 9 12 15 18 9"></polyline>
  </svg>
);

const RowExpanderIcon = ({ expanded }: { expanded: boolean }) => (
  <span className={`hc-row-expander-arrow${expanded ? ' is-expanded' : ''}`} aria-hidden="true">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="6 9 12 15 18 9"></polyline>
    </svg>
  </span>
);

const SearchIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
  </svg>
);

const ArrowDownIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="12" y1="5" x2="12" y2="19" />
    <polyline points="5 12 12 19 19 12" />
  </svg>
);

function parseConditionDescription(description: string): ParsedDescription {
  const normalized = (description || '').replace(/\r\n/g, '\n').trim();
  if (!normalized) return { main: '', inclusion: '', exclusion: '' };

  const inclusionMatch = normalized.match(/\bInclusions?:/i);
  const exclusionMatch = normalized.match(/\bExclusions?:/i);

  const firstMarkerIndex = [inclusionMatch?.index, exclusionMatch?.index]
    .filter((index): index is number => index != null)
    .sort((a, b) => a - b)[0];

  const main = (firstMarkerIndex == null ? normalized : normalized.slice(0, firstMarkerIndex)).trim();

  let inclusion = '';
  if (inclusionMatch?.index != null) {
    const start = inclusionMatch.index + inclusionMatch[0].length;
    const end = exclusionMatch?.index != null && exclusionMatch.index > inclusionMatch.index
      ? exclusionMatch.index
      : normalized.length;
    inclusion = normalized.slice(start, end).trim();
  }

  let exclusion = '';
  if (exclusionMatch?.index != null) {
    const start = exclusionMatch.index + exclusionMatch[0].length;
    exclusion = normalized.slice(start).trim();
  }

  return { main, inclusion, exclusion };
}

export default function HealthConditionWizard({ workerId, currentConditions, allCoreSets, onClose, onSaved, onStepChange }: HealthConditionWizardProps) {
  const [step, setStep] = useState<Step>('select');
  const [allIcfCodes, setAllIcfCodes] = useState<IcfCodeEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState('');
  const [reviewSearch, setReviewSearch] = useState('');
  const [coreSetFilterOpen, setCoreSetFilterOpen] = useState(false);
  const [wizardSelectedCoreSets, setWizardSelectedCoreSets] = useState<string[]>([]);
  const [categoryFilterOpen, setCategoryFilterOpen] = useState(false);
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [expandedReviewCode, setExpandedReviewCode] = useState<string | null>(null);
  const [showScrollToast, setShowScrollToast] = useState(false);
  const [showMissingValueToast, setShowMissingValueToast] = useState(false);
  const [showSavedToast, setShowSavedToast] = useState(false);
  const [scrollToastDismissedStep, setScrollToastDismissedStep] = useState<Step | null>(null);
  const coreSetFilterRef = useRef<HTMLDivElement>(null);
  const categoryFilterRef = useRef<HTMLDivElement>(null);
  const selectScrollRef = useRef<HTMLDivElement>(null);
  const reviewScrollRef = useRef<HTMLDivElement>(null);

  // Each category maps a display label to the ICF code first-character prefix.
  // The filter state stores prefixes ('b', 'd', …) — never label strings.
  const CATEGORIES = [
    { label: 'Body Functions', prefix: 'b' },
    { label: 'Activities and Participation', prefix: 'd' },
  ];

  // Set of icf_codes that are checked (including currently assigned + newly selected)
  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set());

  // Map of icf_code -> new qualifier assigned in Step 2. Defaulting to null.
  const [assignedQualifiers, setAssignedQualifiers] = useState<Record<string, number | null>>({});

  useEffect(() => {
    onStepChange?.(step);
  }, [onStepChange, step]);

  useEffect(() => {
    setScrollToastDismissedStep(null);
    setShowScrollToast(false);
    setShowMissingValueToast(false);
  }, [step]);

  useEffect(() => {
    const hasOpenFilter = coreSetFilterOpen || categoryFilterOpen;
    if (!hasOpenFilter) return;

    function handleClickOutside(event: MouseEvent) {
      const target = event.target as Node;

      if (coreSetFilterOpen && coreSetFilterRef.current && !coreSetFilterRef.current.contains(target)) {
        setCoreSetFilterOpen(false);
      }

      if (categoryFilterOpen && categoryFilterRef.current && !categoryFilterRef.current.contains(target)) {
        setCategoryFilterOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setCoreSetFilterOpen(false);
        setCategoryFilterOpen(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [coreSetFilterOpen, categoryFilterOpen]);

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
          description: code.description || '',
          core_sets: [...new Set(code.core_sets || [])],
        });
        return;
      }

      byCode.set(code.icf_code, {
        ...existing,
        icf_name: existing.icf_name || code.icf_name,
        description: existing.description || code.description || '',
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
      wizardSelectedCoreSets.every(cs => (c.core_sets || []).includes(cs));
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
      const hasMissingNewCodeValue = Array.from(selectedCodes).some(code => !currentSet.has(code) && assignedQualifiers[code] == null);
      if (hasMissing) {
        setShowMissingValueToast(hasMissingNewCodeValue);
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
        setShowSavedToast(true);
        setStep('done');
        setTimeout(() => {
          onSaved();
          onClose();
        }, 1800);
      } catch (err: any) {
        setError(err.message || 'Failed to save changes.');
        setStep('review');
      }
    }
  };

  // Groups for review step
  const currentSet = useMemo(() => new Set(currentConditions.map(c => c.icf_code)), [currentConditions]);

  const reviewSearchQuery = reviewSearch.toLowerCase();
  const filterReview = (c: { icf_code: string; icf_name?: string }) => {
    if (!reviewSearchQuery) return true;
    return c.icf_code.toLowerCase().includes(reviewSearchQuery) || (c.icf_name || '').toLowerCase().includes(reviewSearchQuery);
  };

  const getPreviousQualifier = (icfCode: string) => {
    const currentCondition = currentConditions.find(x => x.icf_code === icfCode);
    return currentCondition?.bf_qualifier ?? currentCondition?.ap1_qualifier ?? null;
  };

  const hasQualifierChanged = (icfCode: string) => {
    const previousQualifier = getPreviousQualifier(icfCode);
    const nextQualifier = assignedQualifiers[icfCode] ?? null;
    return previousQualifier !== null && nextQualifier !== null && previousQualifier !== nextQualifier;
  };

  const getReviewDescription = (icfCode: string) => {
    const currentDescription = currentConditions.find(x => x.icf_code === icfCode)?.description;
    const catalogDescription = normalizedIcfCodes.find(x => x.icf_code === icfCode)?.description;
    return currentDescription || catalogDescription || '';
  };

  const toggleReviewExpansion = (icfCode: string) => {
    setExpandedReviewCode(prev => prev === icfCode ? null : icfCode);
  };

  const toModify = normalizedIcfCodes.filter(c => currentSet.has(c.icf_code) && selectedCodes.has(c.icf_code) && filterReview(c));
  const toAdd = normalizedIcfCodes.filter(c => !currentSet.has(c.icf_code) && selectedCodes.has(c.icf_code) && filterReview(c));
  const toRemove = currentConditions.filter(c => !selectedCodes.has(c.icf_code) && filterReview(c));

  useEffect(() => {
    const activeContainer = step === 'select'
      ? selectScrollRef.current
      : step === 'review'
        ? reviewScrollRef.current
        : null;

    if (!activeContainer || scrollToastDismissedStep === step) {
      setShowScrollToast(false);
      return;
    }

    const updateScrollToast = () => {
      const hasOverflow = activeContainer.scrollHeight - activeContainer.clientHeight > 8;
      const hasMoreBelow = activeContainer.scrollTop + activeContainer.clientHeight < activeContainer.scrollHeight - 8;
      setShowScrollToast(hasOverflow && hasMoreBelow);
    };

    updateScrollToast();
    activeContainer.addEventListener('scroll', updateScrollToast);
    window.addEventListener('resize', updateScrollToast);

    return () => {
      activeContainer.removeEventListener('scroll', updateScrollToast);
      window.removeEventListener('resize', updateScrollToast);
    };
  }, [
    step,
    loading,
    filteredCodes.length,
    toModify.length,
    toAdd.length,
    toRemove.length,
    expandedReviewCode,
    scrollToastDismissedStep,
  ]);

  useEffect(() => {
    if (!showSavedToast) return;
    const timer = window.setTimeout(() => setShowSavedToast(false), 2200);
    return () => window.clearTimeout(timer);
  }, [showSavedToast]);


  return (
    <div className="hc-wizard-overlay">
      <div className="hc-wizard-modal">
        {/* Header */}
        <div className="hc-wizard-header">
          <div>
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
              <div className="hc-wizard-toolbar">
                <div className="hc-search-wrapper">
                  <span className="hc-search-icon"><SearchIcon /></span>
                  <input
                    type="text"
                    className="hc-search-input"
                    placeholder="Search..."
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                  />
                </div>

                {/* Filters Group */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-muted)', fontSize: '0.8rem', fontWeight: 500 }}>
                    <FilterIcon /> Filters:
                  </div>

                  {/* Core Set filter */}
                  <div ref={coreSetFilterRef} style={{ position: 'relative' }}>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        if (!coreSetFilterOpen) setCategoryFilterOpen(false);
                        setCoreSetFilterOpen(v => !v);
                      }}
                      className={`hc-filter-btn ${coreSetFilterOpen || wizardSelectedCoreSets.length > 0 ? 'active' : ''}`}
                      title="Filter by Core Set"
                    >
                      Core Set
                      {wizardSelectedCoreSets.length > 0 && (
                        <span style={{
                          background: '#4DD9C0', color: '#0f2233', borderRadius: '99px',
                          fontSize: '0.7rem', fontWeight: 700, padding: '1px 7px',
                        }}>{wizardSelectedCoreSets.length}</span>
                      )}
                      <ChevronDownIcon />
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

                  {/* Category filter */}
                  <div ref={categoryFilterRef} style={{ position: 'relative' }}>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        if (!categoryFilterOpen) setCoreSetFilterOpen(false);
                        setCategoryFilterOpen(v => !v);
                      }}
                      className={`hc-filter-btn ${categoryFilterOpen || selectedCategories.length > 0 ? 'active' : ''}`}
                      title="Filter by Category"
                    >
                      Category
                      {selectedCategories.length > 0 && (
                        <span style={{
                          background: '#4DD9C0', color: '#0f2233', borderRadius: '99px',
                          fontSize: '0.7rem', fontWeight: 700, padding: '1px 7px',
                        }}>{selectedCategories.length}</span>
                      )}
                      <ChevronDownIcon />
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
                </div>
              </div>

              <div ref={selectScrollRef} className="hc-wizard-table-container">
                {loading ? (
                  <div className="hc-wizard-loading">Loading ICF codes...</div>
                ) : (
                  <table className="hc-wizard-table">
                    <thead>
                      <tr>
                        <th style={{ width: 60 }}><CheckIcon /></th>
                        <th style={{ width: 140 }}>ICF Code</th>
                        <th>Code Name</th>
                        <th>Category</th>
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
            <>
              <div className="hc-review-toolbar">
                <h4 className="hc-group-title hc-group-title--toolbar">Codes to be modified</h4>
                <div className="hc-search-wrapper hc-search-wrapper--review">
                  <span className="hc-search-icon"><SearchIcon /></span>
                  <input
                    type="text"
                    className="hc-search-input"
                    placeholder="Search..."
                    value={reviewSearch}
                    onChange={e => setReviewSearch(e.target.value)}
                  />
                </div>
              </div>
              <div ref={reviewScrollRef} className="hc-wizard-review-container">

              {toModify.length > 0 && (
                <div className="hc-review-group">
                  <div className="hc-review-table-wrapper">
                    <ReviewTableHeader />
                    {toModify.map(c => {
                      const prevQ = getPreviousQualifier(c.icf_code);
                      const showPrevious = hasQualifierChanged(c.icf_code);
                      const isExpanded = expandedReviewCode === c.icf_code;
                      const description = getReviewDescription(c.icf_code);
                      const parsedDescription = parseConditionDescription(description);
                      return (
                        <ReviewExpandableRow
                          key={c.icf_code}
                          icfCode={c.icf_code}
                          icfName={c.icf_name}
                          description={description}
                          parsedDescription={parsedDescription}
                          isExpanded={isExpanded}
                          isError={assignedQualifiers[c.icf_code] == null}
                          statusBadge={<span className="hc-status-badge hc-badge-modify">Modify</span>}
                          qualifierContent={(
                            <QualifierSelector
                              val={assignedQualifiers[c.icf_code] ?? null}
                              onChange={(q) => handleQualifierSelect(c.icf_code, q)}
                              allowZero={true}
                            />
                          )}
                          previousContent={showPrevious ? prevQ : '-'}
                          onToggle={() => toggleReviewExpansion(c.icf_code)}
                        />
                      );
                    })}
                  </div>
                </div>
              )}

              {toAdd.length > 0 && (
                <div className="hc-review-group">
                  <h4 className="hc-group-title">New added codes</h4>
                  <div className="hc-review-table-wrapper">
                    <ReviewTableHeader />
                    {toAdd.map(c => {
                      const isExpanded = expandedReviewCode === c.icf_code;
                      const description = getReviewDescription(c.icf_code);
                      const parsedDescription = parseConditionDescription(description);
                      return (
                        <ReviewExpandableRow
                          key={c.icf_code}
                          icfCode={c.icf_code}
                          icfName={c.icf_name}
                          description={description}
                          parsedDescription={parsedDescription}
                          isExpanded={isExpanded}
                          isError={assignedQualifiers[c.icf_code] == null}
                          statusBadge={<span className="hc-status-badge hc-badge-add">New addition</span>}
                          qualifierContent={(
                            <QualifierSelector
                              val={assignedQualifiers[c.icf_code] ?? null}
                              onChange={(q) => handleQualifierSelect(c.icf_code, q)}
                            />
                          )}
                          previousContent={'-'}
                          onToggle={() => toggleReviewExpansion(c.icf_code)}
                        />
                      );
                    })}
                  </div>
                </div>
              )}

              {toRemove.length > 0 && (
                <div className="hc-review-group">
                  <h4 className="hc-group-title">Codes to be removed</h4>
                  <div className="hc-review-table-wrapper">
                    <ReviewTableHeader />
                    {toRemove.map(c => {
                      const isExpanded = expandedReviewCode === c.icf_code;
                      const description = c.description || '';
                      const parsedDescription = parseConditionDescription(description);
                      return (
                        <ReviewExpandableRow
                          key={c.icf_code}
                          icfCode={c.icf_code}
                          icfName={c.icf_name}
                          description={description}
                          parsedDescription={parsedDescription}
                          isExpanded={isExpanded}
                          isDimmed={true}
                          statusBadge={<span className="hc-status-badge hc-badge-remove">For removal</span>}
                          qualifierContent={'-'}
                          previousContent={'-'}
                          onToggle={() => toggleReviewExpansion(c.icf_code)}
                        />
                      );
                    })}
                  </div>
                </div>
              )}

              {toModify.length === 0 && toAdd.length === 0 && toRemove.length === 0 && (
                <div className="hc-review-empty">
                  {reviewSearch ? 'No codes match your search.' : 'No changes made.'}
                </div>
              )}
            </div>
            </>
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

        <div className="hc-toast-stack" aria-live="polite">
          {showScrollToast && (
            <div className="hc-toast hc-toast--info">
              <span className="hc-toast-message">More lines below - Scroll down</span>
              <span className="hc-toast-icon" aria-hidden="true"><ArrowDownIcon /></span>
              <button
                type="button"
                className="hc-toast-close"
                aria-label="Dismiss scroll hint"
                onClick={() => {
                  setShowScrollToast(false);
                  setScrollToastDismissedStep(step);
                }}
              >
                <CloseIcon />
              </button>
            </div>
          )}

          {showSavedToast && (
            <div className="hc-toast hc-toast--success">
              <span className="hc-toast-message">All changes are saved.</span>
              <button
                type="button"
                className="hc-toast-close"
                aria-label="Dismiss saved message"
                onClick={() => setShowSavedToast(false)}
              >
                <CloseIcon />
              </button>
            </div>
          )}

          {showMissingValueToast && (
            <div className="hc-toast hc-toast--error">
              <span className="hc-toast-message">Changes couldn&apos;t be saved.</span>
              <button
                type="button"
                className="hc-toast-close"
                aria-label="Dismiss save error"
                onClick={() => setShowMissingValueToast(false)}
              >
                <CloseIcon />
              </button>
            </div>
          )}
        </div>

      </div>
    </div>
  );
}

function ReviewExpandableRow({
  icfCode,
  icfName,
  description,
  parsedDescription,
  isExpanded,
  isError = false,
  isDimmed = false,
  statusBadge,
  qualifierContent,
  previousContent,
  onToggle,
}: {
  icfCode: string;
  icfName: string;
  description: string;
  parsedDescription: ParsedDescription;
  isExpanded: boolean;
  isError?: boolean;
  isDimmed?: boolean;
  statusBadge: ReactNode;
  qualifierContent: ReactNode;
  previousContent: ReactNode;
  onToggle: () => void;
}) {
  return (
    <>
      <div
        className={`hc-review-row${isExpanded ? ' is-expanded' : ''}${isError ? ' hc-row-error' : ''}${isDimmed ? ' hc-row-dimmed' : ''}`}
        onClick={onToggle}
      >
        <div className="col-code hc-table-code">
          <div className="hc-review-code-cell">
            <RowExpanderIcon expanded={isExpanded} />
            <span>{icfCode}</span>
          </div>
        </div>
        <div className="col-name">{icfName}</div>
        <div className="col-status">{statusBadge}</div>
        <div className="col-qualifier">{qualifierContent}</div>
        <div className="col-prev">{previousContent}</div>
      </div>
      {isExpanded && (
        <div className="hc-review-detail-row">
          <div className="col-code" />
          <div className="col-name hc-review-detail-content">
            <div className="hc-review-description">
              {description ? (
                <>
                  {parsedDescription.main && (
                    <p className="hc-review-description-main">{parsedDescription.main}</p>
                  )}
                  {parsedDescription.inclusion && (
                    <div className="hc-review-description-section">
                      <div className="hc-review-description-label">Inclusion</div>
                      <p className="hc-review-description-text">{parsedDescription.inclusion}</p>
                    </div>
                  )}
                  {parsedDescription.exclusion && (
                    <div className="hc-review-description-section">
                      <div className="hc-review-description-label">Exclusion</div>
                      <p className="hc-review-description-text">{parsedDescription.exclusion}</p>
                    </div>
                  )}
                </>
              ) : (
                'No ontology description available for this ICF code.'
              )}
            </div>
          </div>
          <div className="col-status" />
          <div className="col-qualifier" />
          <div className="col-prev" />
        </div>
      )}
    </>
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
          onClick={(e) => { e.stopPropagation(); onChange(q); }}
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
      <div className="col-code">ICF Code</div>
      <div className="col-name">Code Name</div>
      <div className="col-status">Status</div>
      <div className="col-qualifier">Qualifier</div>
      <div className="col-prev">Previous</div>
    </div>
  );
}
