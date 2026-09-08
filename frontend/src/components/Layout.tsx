import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Button, Dropdown, Menu } from 'antd';
import {
  BookOutlined,
  ClusterOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  HomeOutlined,
  LogoutOutlined,
  MedicineBoxOutlined,
  MenuOutlined,
  RobotOutlined,
  SettingOutlined,
  SolutionOutlined,
  UserOutlined,
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
  { key: '/cases', icon: <SolutionOutlined />, label: '无效/加重医案' },
  { key: '/clauses', icon: <BookOutlined />, label: '无效/加重条文' },
  { key: '/agent', icon: <RobotOutlined />, label: 'Agent 工作台' },
];

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, isAuthenticated, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  const selectedKey = `/${  location.pathname.split('/')[1] || ''}`;
  const isAgentWorkspace = selectedKey === '/agent';

  const userMenuItems = isAuthenticated
    ? [
        ...(user?.role === 'admin'
          ? [{ key: 'users', icon: <UserOutlined />, label: '用户管理', onClick: () => navigate('/users') },
             { key: 'llm-config', icon: <SettingOutlined />, label: 'LLM 配置', onClick: () => navigate('/config/llm') },
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

      {mobileOpen ? (
        <div className={styles.mobileMenu}>
          <Menu
            mode="vertical"
            selectedKeys={[selectedKey]}
            items={navItems}
            onClick={({ key }) => { navigate(key); setMobileOpen(false); }}
            style={{ border: 'none' }}
          />
        </div>
      ) : null}

      <main className={`${styles.main} ${isAgentWorkspace ? styles.agentMain : ''}`}>
        <Outlet />
      </main>

      {!isAgentWorkspace && (
        <footer className={styles.footer}>
          <div className={styles.footerContent}>
            <section className={styles.footerColumn} aria-labelledby="footer-about-title">
              <h2 id="footer-about-title" className={styles.footerTitle}>关于平台</h2>
              <span className={styles.footerTitleAccent} />
              <Link className={styles.footerLink} to="/">平台介绍</Link>
            </section>

            <section className={styles.footerColumn} aria-labelledby="footer-services-title">
              <h2 id="footer-services-title" className={styles.footerTitle}>服务支持</h2>
              <span className={styles.footerTitleAccent} />
              <nav className={styles.footerLinks} aria-label="服务支持">
                <Link className={styles.footerLink} to="/compounds">毒性化合物</Link>
                <Link className={styles.footerLink} to="/herbs">毒性中药</Link>
                <Link className={styles.footerLink} to="/couplets">毒性药对</Link>
                <Link className={styles.footerLink} to="/decoctions">毒性方剂</Link>
                <Link className={styles.footerLink} to="/cases">治疗无效/加重的医案</Link>
                <Link className={styles.footerLink} to="/clauses">治疗无效/加重的条文及论述</Link>
              </nav>
            </section>

            <section className={styles.footerColumn} aria-labelledby="footer-contact-title">
              <h2 id="footer-contact-title" className={styles.footerTitle}>联系我们</h2>
              <span className={styles.footerTitleAccent} />
              <address className={styles.contactList}>
                <span>地址：北京市朝阳区北三环东路11号</span>
                <span>电话：010-53911430</span>
                <span>邮箱：{'cyh@bucm.edu.cn'}</span>
              </address>
            </section>
          </div>

          <div className={styles.footerBottom}>
            <div>© 2025 中药毒理与循证数据库 版权所有 <span className={styles.separator}>|</span> 京ICP备2025140844号</div>
            <div className={styles.citation}>
              推荐引用：陈俞含，马天伊，刘兆兰，张思苒，袁孟泽，孙光卉. 中药毒理与循证平台 V1.0 （计算机软件）[CP]. 2025.
            </div>
          </div>
        </footer>
      )}
    </div>
  );
}
