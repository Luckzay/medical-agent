import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import HomePage from './pages/HomePage';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import HerbList from './pages/HerbList';
import HerbDetail from './pages/HerbDetail';
import DecoctionList from './pages/DecoctionList';
import DecoctionDetail from './pages/DecoctionDetail';
import CoupletList from './pages/CoupletList';
import CoupletDetail from './pages/CoupletDetail';
import CompoundList from './pages/CompoundList';
import CompoundDetail from './pages/CompoundDetail';
import ExpertiseList from './pages/ExpertiseList';
import ExpertiseDetail from './pages/ExpertiseDetail';
import PaperList from './pages/PaperList';
import PaperDetail from './pages/PaperDetail';
import UserManagement from './pages/UserManagement';
import { useAuth } from './hooks/useAuth';

function AdminRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, user } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (user?.role !== 'admin') return <Navigate to="/" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route element={<Layout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/herbs" element={<HerbList />} />
        <Route path="/herbs/:id" element={<HerbDetail />} />
        <Route path="/decoctions" element={<DecoctionList />} />
        <Route path="/decoctions/:id" element={<DecoctionDetail />} />
        <Route path="/couplets" element={<CoupletList />} />
        <Route path="/couplets/:id" element={<CoupletDetail />} />
        <Route path="/compounds" element={<CompoundList />} />
        <Route path="/compounds/:id" element={<CompoundDetail />} />
        <Route path="/expertises" element={<ExpertiseList />} />
        <Route path="/expertises/:id" element={<ExpertiseDetail />} />
        <Route path="/papers" element={<PaperList />} />
        <Route path="/papers/:id" element={<PaperDetail />} />
        <Route path="/users" element={<AdminRoute><UserManagement /></AdminRoute>} />
      </Route>
    </Routes>
  );
}
