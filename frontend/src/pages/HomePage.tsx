import { useNavigate } from 'react-router-dom';
import { Row, Col, Button, Typography, Space, Statistic } from 'antd';
import {
  ExperimentOutlined,
  MedicineBoxOutlined,
  ClusterOutlined,
  FileTextOutlined,
  TeamOutlined,
  ReadOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import styles from './HomePage.module.css';

const { Title, Paragraph } = Typography;

const modules = [
  { key: '/herbs', icon: <ExperimentOutlined />, title: '毒性中药', desc: '浏览毒性中药数据库，查看药效、毒理机制、用药禁忌与临床建议' },
  { key: '/couplets', icon: <ClusterOutlined />, title: '毒性药对', desc: '查阅毒性药对信息，了解配伍毒性、ADR及古籍记载' },
  { key: '/decoctions', icon: <MedicineBoxOutlined />, title: '毒性方剂', desc: '检索方剂毒性数据，查看Meta分析、临床试验证据' },
  { key: '/compounds', icon: <FileTextOutlined />, title: '毒性化合物', desc: '查询化合物化学信息、FDA药理学综述、LiverTox摘要' },
  { key: '/expertises', icon: <TeamOutlined />, title: '专家经验', desc: '汇集名家用药经验、临床应用案例与相关文献' },
  { key: '/papers', icon: <ReadOutlined />, title: '文献证据', desc: '检索相关研究论文，获取药效与毒性循证依据' },
];

export default function HomePage() {
  const navigate = useNavigate();

  return (
    <div>
      <div className={styles.hero}>
        <Title level={2} className={styles.heroTitle}>
          中药毒理与循证数据库平台
        </Title>
        <Paragraph className={styles.heroDesc}>
          专业的中药安全性评估与用药参考平台，集成毒性化合物、毒性中药、毒性药对、
          毒性方剂及专家经验等多维度数据，助力中医药研究、临床合理用药与科研决策。
        </Paragraph>
        <Space>
          <Button type="primary" icon={<SearchOutlined />} onClick={() => navigate('/herbs')}>
            开始检索
          </Button>
          <Button onClick={() => navigate('/decoctions')}>浏览方剂</Button>
        </Space>
      </div>

      <div className={styles.stats}>
        <Row gutter={[16, 24]}>
          {[
            { icon: <SafetyCertificateOutlined />, label: '毒性中药', value: '—' },
            { icon: <ClusterOutlined />, label: '毒性药对', value: '—' },
            { icon: <MedicineBoxOutlined />, label: '毒性方剂', value: '—' },
            { icon: <FileTextOutlined />, label: '毒性化合物', value: '—' },
          ].map((s) => (
            <Col xs={12} sm={6} key={s.label}>
              <div className={styles.statItem}>
                <Statistic valueStyle={{ color: '#1a1a1a', fontSize: 28 }} prefix={s.icon} value={s.value} />
                <div className={styles.statLabel}>{s.label}</div>
              </div>
            </Col>
          ))}
        </Row>
      </div>

      <div className={styles.modules}>
        <Title level={3} className={styles.modulesTitle}>数据模块</Title>
        <Row gutter={[16, 16]}>
          {modules.map((m) => (
            <Col xs={24} sm={12} md={8} key={m.key}>
              <div className={styles.moduleCard} onClick={() => navigate(m.key)}>
                <div className={styles.moduleIcon}>{m.icon}</div>
                <div className={styles.moduleTitle}>{m.title}</div>
                <div className={styles.moduleDesc}>{m.desc}</div>
              </div>
            </Col>
          ))}
        </Row>
      </div>
    </div>
  );
}
