import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import Dashboard from './pages/Dashboard'
import Writing from './pages/Writing'
import Search from './pages/Search'
import Library from './pages/Library'
import DocumentDetail from './pages/DocumentDetail'
import Style from './pages/Style'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="writing" element={<Writing />} />
        <Route path="search" element={<Search />} />
        <Route path="library" element={<Library />} />
        <Route path="library/:docId" element={<DocumentDetail />} />
        <Route path="style" element={<Style />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
