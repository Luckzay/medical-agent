import { useNavigate } from 'react-router-dom';
import { Button, Col, Row, Space, Statistic, Typography } from 'antd';
import {
  BookOutlined,
  ClusterOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  MedicineBoxOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  SolutionOutlined,
} from '@ant-design/icons';
import styles from './HomePage.module.css';

const { Title, Paragraph } = Typography;

const modules = [
  { key: '/herbs', icon: <ExperimentOutlined />, title: '毒性中药', desc: '浏览毒性中药数据库，查看药效、毒理机制、用药禁忌与临床建议' },
  { key: '/couplets', icon: <ClusterOutlined />, title: '毒性药对', desc: '查阅毒性药对信息，了解配伍毒性、ADR及古籍记载' },
  { key: '/decoctions', icon: <MedicineBoxOutlined />, title: '毒性方剂', desc: '检索方剂毒性数据、用药禁忌与临床试验证据' },
  { key: '/compounds', icon: <FileTextOutlined />, title: '毒性化合物', desc: '查询化合物化学信息、FDA药理学综述、LiverTox摘要' },
  { key: '/cases', icon: <SolutionOutlined />, title: '治疗无效/加重的医案', desc: '查阅治疗无效或病情加重的医案及其关联中药、方剂' },
  { key: '/clauses', icon: <BookOutlined />, title: '治疗无效/加重的条文及论述', desc: '查阅治疗无效或加重相关的经典条文、辨析与论述' },
  { key: '/agent', icon: <RobotOutlined />, title: 'Agent 工作台', desc: '通过自然语言开放问答、查询数据库，并实时查看科研分析执行轨迹' },
];

export default function HomePage() {
  const navigate = useNavigate();

  return (
    <div>
      <div className={styles.hero}>
        <Title level={2} className={styles.heroTitle}>
          中药毒理与循证平台V1.0
        </Title>
        <Paragraph className={styles.heroDesc}>
          专业的中药安全性评估与用药参考平台，集成毒性化合物、毒性中药、毒性药对、
          毒性方剂及治疗无效或加重记录等多维度数据，助力中医药研究、临床合理用药与科研决策。
        </Paragraph>
        <Space>
          <Button type="primary" icon={<RobotOutlined />} onClick={() => navigate('/agent')}>
            打开 Agent 工作台
          </Button>
          <Button icon={<SearchOutlined />} onClick={() => navigate('/herbs')}>检索药物</Button>
        </Space>
      </div>

      <section className={styles.introduction} aria-labelledby="platform-introduction-title">
        <Title id="platform-introduction-title" level={3} className={styles.sectionTitle}>平台介绍</Title>
        <Paragraph className={styles.introductionText}>
          中药毒理与循证平台V1.0 由北京中医药大学循证医学中心团队研发，聚焦于毒性中药的化学成分、
          药理/毒理实验结果、毒性中药人用经验、毒性方剂及中成药的临床应用系统评价，构建毒性中药的
          “分子研究—专家经验—临床研究与循证”三位一体数据链条，助力毒性中药的安全合理用药和宏观微观多维度研究。
        </Paragraph>
      </section>

      <div className={styles.stats}>
        <div className={styles.statsGrid}>
          {[
            { icon: <FileTextOutlined />, label: '毒性化学成分', value: 236, suffix: '种' },
            { icon: <SafetyCertificateOutlined />, label: '毒性中药', value: 92, suffix: '味' },
            { icon: <ClusterOutlined />, label: '中药配伍', value: 24, suffix: '对' },
            { icon: <MedicineBoxOutlined />, label: '常用含毒方剂', value: 83, suffix: '个' },
            { icon: <SolutionOutlined />, label: '国医大师与名老中医经验', value: 312, suffix: '位' },
          ].map((stat) => (
            <div className={styles.statItem} key={stat.label}>
              <Statistic
                valueStyle={{ color: '#1a1a1a', fontSize: 28 }}
                prefix={stat.icon}
                value={stat.value}
                suffix={stat.suffix}
              />
              <div className={styles.statLabel}>{stat.label}</div>
            </div>
          ))}
        </div>
      </div>

      <div className={styles.modules}>
        <Title level={3} className={styles.sectionTitle}>数据模块</Title>
        <Row gutter={[16, 16]}>
          {modules.map((module) => (
            <Col xs={24} sm={12} md={8} key={module.key}>
              <div className={styles.moduleCard} onClick={() => navigate(module.key)}>
                <div className={styles.moduleIcon}>{module.icon}</div>
                <div className={styles.moduleTitle}>{module.title}</div>
                <div className={styles.moduleDesc}>{module.desc}</div>
              </div>
            </Col>
          ))}
        </Row>
      </div>

      <section className={styles.team} aria-labelledby="research-team-title">
        <Title id="research-team-title" level={3} className={styles.sectionTitle}>研发团队</Title>
        <div className={styles.teamContent}>
          <div className={styles.teamName}>北京中医药大学循证医学中心团队</div>
          <Paragraph className={styles.teamDescription}>
            数据库由北京中医药大学循证医学中心团队研发。团队长期致力于中药安全性评价与循证医学研究，
            结合现代信息技术与传统中医药理论，构建了这一综合性数据库平台，为毒性中药的安全合理使用提供科学依据。
          </Paragraph>
        </div>
      </section>
    </div>
  );
}
