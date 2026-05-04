import { Routes, Route, NavLink } from 'react-router-dom';
import { Upload as UploadIcon, Search, Database } from 'lucide-react';
import UploadPage from './pages/Upload';
import SearchPage from './pages/Search';

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Navbar */}
      <nav className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center gap-3">
          <img src="/argos.svg" alt="Argos" className="w-8 h-8" />
          <span className="text-xl font-bold text-gray-900">Argos</span>
          <span className="text-xs px-2 py-0.5 bg-argos-100 text-argos-700 rounded-full font-medium">
            RAG
          </span>
        </div>
        <div className="flex items-center gap-1">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              `flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-argos-50 text-argos-700'
                  : 'text-gray-600 hover:bg-gray-100'
              }`
            }
          >
            <UploadIcon size={16} />
            Upload
          </NavLink>
          <NavLink
            to="/search"
            className={({ isActive }) =>
              `flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-argos-50 text-argos-700'
                  : 'text-gray-600 hover:bg-gray-100'
              }`
            }
          >
            <Search size={16} />
            Cerca
          </NavLink>
        </div>
      </nav>

      {/* Content */}
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<UploadPage />} />
          <Route path="/search" element={<SearchPage />} />
        </Routes>
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-200 bg-white px-6 py-3 text-center text-xs text-gray-400">
        Argos v0.1.0 — Modular RAG System
      </footer>
    </div>
  );
}
