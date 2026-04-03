import { useState } from 'react'
import './index.css'
import HomePage from './components/HomePage'
import WorkersPage from './components/WorkersPage'

type Page = 'home' | 'workers'

function App() {
  const [page, setPage] = useState<Page>('home')

  if (page === 'workers') {
    return <WorkersPage onNavigateHome={() => setPage('home')} />
  }

  return <HomePage onNavigate={(id) => {
    if (id === 'worker-information') setPage('workers')
  }} />
}

export default App
