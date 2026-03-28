import './HomePage.css';

interface NavCard {
  id: string;
  icon: React.ReactNode;
  title: string;
  description: string[];
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
    <rect x="28" y="10" width="30" height="26" rx="3" fill="white" opacity="0.9" />
    <line x1="43" y1="36" x2="43" y2="44" stroke="white" strokeWidth="2" opacity="0.8" />
    <line x1="36" y1="44" x2="50" y2="44" stroke="white" strokeWidth="2" opacity="0.8" />
    {/* Chart line going up */}
    <polyline points="32,30 38,22 45,26 54,14" stroke="#4DD9C0" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    {/* Arrow head */}
    <polyline points="50,11 54,14 51,18" stroke="#4DD9C0" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" fill="none" />
  </svg>
);

const JobPositionsIcon = () => (
  <svg width="64" height="64" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
    {/* Briefcase body */}
    <rect x="8" y="22" width="48" height="34" rx="4" fill="none" stroke="white" strokeWidth="2.5" />
    {/* Briefcase handle */}
    <path d="M22 22V18a4 4 0 0 1 4-4h12a4 4 0 0 1 4 4v4" stroke="white" strokeWidth="2.5" strokeLinecap="round" fill="none" />
    {/* Center divider */}
    <line x1="8" y1="38" x2="56" y2="38" stroke="white" strokeWidth="2" opacity="0.6" />
    {/* Latch */}
    <rect x="27" y="33" width="10" height="10" rx="2" fill="none" stroke="white" strokeWidth="2" />
    {/* Plus symbol inside */}
    <line x1="32" y1="35.5" x2="32" y2="40.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
    <line x1="29.5" y1="38" x2="34.5" y2="38" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
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

export default function HomePage() {
  return (
    <div className="home-page">
      {/* Animated background blobs */}
      <div className="bg-blob bg-blob-1" />
      <div className="bg-blob bg-blob-2" />
      <div className="bg-blob bg-blob-3" />

      {/* Header / Brand */}
      <header className="home-header">
        <div className="brand">
          <img src="/logo-rientra.png" alt="Rientra Logo" className="brand-logo" />
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
            <button key={card.id} className="nav-card" id={card.id} aria-label={card.title}>
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
          <img src="/logo-stiima.png" alt="STIIMA CNR Logo" className="footer-logo footer-logo-stiima" />
          <img src="/logo-inail.png" alt="INAIL Logo" className="footer-logo footer-logo-inail" />
        </div>
      </footer>
    </div>
  );
}
