import './HomePage.css';

interface NavCard {
  id: string;
  icon: React.ReactNode;
  title: string;
  description: string[];
}

interface HomePageProps {
  onNavigate?: (cardId: string) => void;
}

const WorkerIcon = () => (
  <svg width="64" height="64" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
    {/* Front person */}
    <circle cx="26" cy="18" r="9" fill="#4DD9C0" />
    <path d="M10 46c0-9 7-16 16-16s16 7 16 16" fill="#4DD9C0" />
    {/* Back person - slightly offset */}
    <circle cx="36" cy="16" r="8" fill="#60C8B0" opacity="0.8" />
    <path d="M20 44c0-8.5 6.7-15 15-15s15 6.5 15 15" fill="#60C8B0" opacity="0.8" />
    {/* ID card */}
    <rect x="18" y="42" width="26" height="18" rx="3" fill="white" opacity="0.9" />
    <rect x="22" y="46" width="8" height="6" rx="1" fill="#4DD9C0" />
    <rect x="33" y="47" width="8" height="2" rx="1" fill="#aaa" />
    <rect x="33" y="51" width="5" height="2" rx="1" fill="#ccc" />
  </svg>
);

const JobAnalysisIcon = () => (
  <svg width="64" height="64" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
    {/* Person */}
    <circle cx="18" cy="22" r="8" fill="#4DD9C0" />
    <path d="M6 44c0-7.5 5.5-12 12-12s12 4.5 12 12" fill="#4DD9C0" />
    {/* Presentation board */}
    <rect x="28" y="10" width="32" height="26" rx="3" fill="white" opacity="0.95" />
    {/* Stand */}
    <line x1="44" y1="36" x2="44" y2="44" stroke="white" strokeWidth="2.5" opacity="0.9" />
    <line x1="37" y1="44" x2="51" y2="44" stroke="white" strokeWidth="2.5" strokeLinecap="round" opacity="0.9" />
    {/* Chart Axes */}
    <path d="M32 14 V32 H54" stroke="#CBD5E1" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    {/* Chart Line */}
    <path d="M32 30 L39 21 L45 25 L53 14" stroke="#4DD9C0" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    {/* Point Markers */}
    <circle cx="32" cy="30" r="2" fill="#1E293B" />
    <circle cx="39" cy="21" r="2" fill="#1E293B" />
    <circle cx="45" cy="25" r="2" fill="#1E293B" />
    <circle cx="53" cy="14" r="2" fill="#1E293B" />
  </svg>
);

const JobPositionsIcon = () => (
  <svg width="64" height="64" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
    {/* Person standing next to the briefcase */}
    <circle cx="18" cy="22" r="8" fill="#4DD9C0" />
    <path d="M6 44c0-7.5 5.5-12 12-12s12 4.5 12 12" fill="#4DD9C0" />
    
    {/* Briefcase Handle */}
    <path d="M37 20V16a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v4" fill="none" stroke="white" strokeWidth="2.5" opacity="0.9" strokeLinecap="round" />
    
    {/* Briefcase Body */}
    <rect x="28" y="20" width="32" height="24" rx="3" fill="white" opacity="0.95" />
    
    {/* Briefcase horizontal seam */}
    <line x1="28" y1="28" x2="60" y2="28" stroke="#E2E8F0" strokeWidth="1" />
    
    {/* Briefcase Latch */}
    <rect x="41" y="25" width="6" height="6" rx="1.5" fill="#1E293B" />
    <rect x="43" y="27" width="2" height="2" rx="0.5" fill="white" />
    
    {/* Decorative details inside the briefcase */}
    <rect x="33" y="34" width="9" height="2" rx="1" fill="#CBD5E1" />
    <rect x="33" y="38" width="5" height="2" rx="1" fill="#CBD5E1" />
    
    {/* Plus badge representing "Import new jobs" */}
    <circle cx="51" cy="35" r="4.5" fill="#4DD9C0" />
    <path d="M49 35h4M51 33v4" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

const cards: NavCard[] = [
  {
    id: 'worker-information',
    icon: <WorkerIcon />,
    title: 'Worker Information',
    description: ['Add new worker,', 'Check current health conditions,', 'Modify health conditions'],
  },
  {
    id: 'job-analysis',
    icon: <JobAnalysisIcon />,
    title: 'Job Analysis',
    description: ['Check and compare job', 'opportunities for workers,', 'List possible work improving aids'],
  },
  {
    id: 'job-positions',
    icon: <JobPositionsIcon />,
    title: 'Job Positions',
    description: ['Check jobs, Import new jobs'],
  },
];

export default function HomePage({ onNavigate }: HomePageProps) {
  return (
    <div className="home-page">
      {/* Animated background blobs */}
      <div className="bg-blob bg-blob-1" />
      <div className="bg-blob bg-blob-2" />
      <div className="bg-blob bg-blob-3" />

      {/* Header / Brand */}
      <header className="home-header">
        <div className="brand">
          <img src="./logo-rientra.png" alt="Rientra Logo" className="brand-logo" />
          <div className="brand-text">
            <span className="brand-title">RIENTR@ returns</span>
            <span className="brand-subtitle">Decision Support System</span>
          </div>
        </div>
      </header>

      {/* Navigation Cards */}
      <main className="home-main">
        <div className="cards-grid">
          {cards.map((card) => (
            <button key={card.id} className="nav-card" id={card.id} aria-label={card.title} onClick={() => onNavigate?.(card.id)}>
              <div className="card-icon-wrapper">
                {card.icon}
              </div>
              <div className="card-body">
                <h2 className="card-title">{card.title}</h2>
                <div className="card-divider" />
                <ul className="card-description">
                  {card.description.map((line, i) => (
                    <li key={i}>{line}</li>
                  ))}
                </ul>
              </div>
              <div className="card-hover-shine" />
            </button>
          ))}
        </div>
      </main>

      {/* Footer Logos */}
      <footer className="home-footer">
        <div className="footer-logos">
          <img src="./logo-stiima.png" alt="STIIMA CNR Logo" className="footer-logo footer-logo-stiima" />
          <img src="./logo-inail.png" alt="INAIL Logo" className="footer-logo footer-logo-inail" />
        </div>
      </footer>
    </div>
  );
}
