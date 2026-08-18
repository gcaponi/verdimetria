import { Routes, Route } from 'react-router'
import HomeNational from './pages/HomeNational'
import DemoPage from './pages/DemoPage'
import AccountPage from './pages/AccountPage'
import MetaPixelRouteTracker from './components/MetaPixelRouteTracker'

export default function App() {
  return (
    <>
    <MetaPixelRouteTracker />
    <Routes>
      <Route path="/" element={<HomeNational />} />
      <Route path="/demo" element={<DemoPage />} />
      <Route path="/account" element={<AccountPage />} />
    </Routes>
    </>
  )
}
