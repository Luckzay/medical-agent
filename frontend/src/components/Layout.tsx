import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Menu, Button, Dropdown } from 'antd';
import {
  HomeOutlined,
  ExperimentOutlined,
  MedicineBoxOutlined,
  ClusterOutlined,
  FileTextOutlined,
  TeamOutlined,
  UserOutlined,
  ReadOutlined,
  LogoutOutlined,
  MenuOutlined,
} from '@ant-design/icons';
import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import styles from './Layout.module.css';

const navItems = [
  { key: '/', icon: <HomeOutlined />, label: '首页' },
  { key: '/herbs', icon: <ExperimentOutlined />, label: '药物' },
  { key: '/couplets', icon: <ClusterOutlined />, label: '药对' },
  { key: '/decoctions', icon: <MedicineBoxOutlined />, label: '方剂' },
  { key: '/compounds', icon: <FileTextOutlined />, label: '化合物' },
  { key: '/expertises', icon: <TeamOutlined />, label: '专家经验' },
  { key: '/papers', icon: <ReadOutlined />, label: '文献' },
];

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, isAuthenticated, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  const selectedKey = '/' + (location.pathname.split('/')[1] || '');

  const userMenuItems = isAuthenticated
    ? [
        ...(user?.role === 'admin'
          ? [{ key: 'users', icon: <UserOutlined />, label: '用户管理', onClick: () => navigate('/users') },
             { type: 'divider' as const }]
          : []),
        { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: logout },
      ]
    : [{ key: 'login', icon: <UserOutlined />, label: '登录', onClick: () => navigate('/login') }];

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <div className={styles.brandGroup}>
          <Button
            type="text"
            icon={<MenuOutlined />}
            onClick={() => setMobileOpen(!mobileOpen)}
            className={styles.mobileNavBtn}
          />
          <span className={styles.brand} onClick={() => navigate('/')}>
            中药毒理与循证数据库
          </span>
        </div>

        <nav className={styles.nav}>
          <div className={styles.desktopNav}>
            <Menu
              mode="horizontal"
              selectedKeys={[selectedKey]}
              items={navItems}
              onClick={({ key }) => navigate(key)}
              style={{ border: 'none', flex: 1, minWidth: 0 }}
            />
          </div>

          <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
            <Button type="text" icon={<UserOutlined />}>
              {user?.full_name || '账户'}
            </Button>
          </Dropdown>
        </nav>
      </header>

      {mobileOpen && (
        <div className={styles.mobileMenu}>
          <Menu
            mode="vertical"
            selectedKeys={[selectedKey]}
            items={navItems}
            onClick={({ key }) => { navigate(key); setMobileOpen(false); }}
            style={{ border: 'none' }}
          />
        </div>
      )}

      <main className={styles.main}>
        <Outlet />
      </main>

      <footer className={styles.footer}>
        中药毒理与循证数据库平台 &copy; {new Date().getFullYear()}
      </footer>
    </div>
  );
}
