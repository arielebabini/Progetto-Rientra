import { useState } from 'react'
import './index.css'
import HomePage from './components/HomePage'
import WorkersPage from './components/WorkersPage'
import UploadOntologyModal from './components/UploadOntologyModal'

type Page = 'home' | 'workers'
export type NavTarget = 'workers' | 'jobs-analysis' | 'jobs-positions'

function App() {
  const [page, setPage] = useState<Page>('home')
  const [initialNav, setInitialNav] = useState<NavTarget>('workers')
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [pendingNav, setPendingNav] = useState<NavTarget | null>(null)

  const handleNavigate = async (id: string) => {
    const electronAPI = (window as any).electronAPI;
    let targetNav: NavTarget = 'workers';
    
    if (id === 'worker-information') {
      targetNav = 'workers';
    } else if (id === 'job-analysis') {
      targetNav = 'jobs-analysis';
    } else if (id === 'job-positions') {
      targetNav = 'jobs-positions';
    }

    if (electronAPI?.checkOntologyExists) {
      const exists = await electronAPI.checkOntologyExists();
      if (!exists) {
        setPendingNav(targetNav);
        setShowUploadModal(true);
        return;
      }
    }

    setInitialNav(targetNav);
    setPage('workers');
  };

  const handleUploadSuccess = () => {
    setShowUploadModal(false);
    if (pendingNav) {
      setInitialNav(pendingNav);
      setPage('workers');
      setPendingNav(null);
    }
  };

  if (page === 'workers') {
    return <WorkersPage onNavigateHome={() => setPage('home')} initialNav={initialNav} />
  }

  return (
    <>
      <HomePage onNavigate={handleNavigate} />
      {showUploadModal && (
        <UploadOntologyModal
          onClose={() => setShowUploadModal(false)}
          onUploadSuccess={handleUploadSuccess}
        />
      )}
    </>
  )
}

export default App

