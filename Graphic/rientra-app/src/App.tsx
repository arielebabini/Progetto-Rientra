import { useState } from 'react'
import './index.css'
import HomePage from './components/HomePage'
import WorkersPage from './components/WorkersPage'

type Page = 'home' | 'workers'
export type NavTarget = 'workers' | 'jobs-analysis' | 'jobs-positions'

function App() {
  const [page, setPage] = useState<Page>('home')
  const [initialNav, setInitialNav] = useState<NavTarget>('workers')

  if (page === 'workers') {
    return <WorkersPage onNavigateHome={() => setPage('home')} initialNav={initialNav} />
  }

  return <HomePage onNavigate={(id) => {
    if (id === 'worker-information') {
      setInitialNav('workers');
      setPage('workers');
    } else if (id === 'job-analysis') {
      setInitialNav('jobs-analysis');
      setPage('workers');
    } else if (id === 'job-positions') {
      setInitialNav('jobs-positions');
      setPage('workers');
    }
  }} />
}

export default App
