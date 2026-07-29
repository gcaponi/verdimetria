import { Routes, Route } from 'react-router'
import HomeNational from './pages/HomeNational'
import DemoPage from './pages/DemoPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomeNational />} />
      <Route path="/demo" element={<DemoPage />} />
    </Routes>
  )
}
