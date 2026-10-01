import React from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Home from './pages/Home.jsx'
import GuardianDashboard from './pages/GuardianDashboard.jsx'
import './index.css'
import './styles.css'
createRoot(document.getElementById('root')).render(
  <BrowserRouter>
    <Routes>
      <Route path="/dashboard/:emergencyId" element={<GuardianDashboard />} />
      <Route path="*" element={<Home />} />
    </Routes>
  </BrowserRouter>
)
