import { Routes, Route } from 'react-router'
import HomeNational from './pages/HomeNational'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomeNational />} />
    </Routes>
  )
}
