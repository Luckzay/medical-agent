import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Typography, Button, Spin, Tag } from 'antd';
import { ArrowLeftOutlined, LinkOutlined } from '@ant-design/icons';
import type { Expertise } from '../types';
import { getExpertiseDetail } from '../services/api';
import Section from '../components/Section';
import styles from './DetailPage.module.css';

const { Title } = Typography;

export default function ExpertiseDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<Expertise | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getExpertiseDetail(Number(id)).then((res) => setData(res.data.data)).finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className={styles.spinWrap}><Spin size="large" /></div>;
  if (!data) return <div className={styles.spinWrap}>未找到该经验记录</div>;

  return (
    <div>
      <Button icon={<ArrowLeftOutlined />} type="text" onClick={() => navigate(-1)} className={styles.backBtn}>
        返回
      </Button>
      <Title level={3} className={styles.pageTitle}>{data.related_article || `经验记录 #${data.id}`}</Title>

      {data.author && (
        <div style={{ marginBottom: 16 }}>
          <Tag>{data.author}</Tag>
          {data.link_article && (
            <a href={data.link_article} target="_blank" rel="noopener noreferrer" style={{ marginLeft: 8 }}>
              <LinkOutlined /> 查看原文
            </a>
          )}
        </div>
      )}

      <Section title="摘要" text={data.abstract} />
      <Section title="涉及药物/方剂" text={data.herb_or_decoction} />
      <Section title="应用场景" text={data.application_situation} />
      <Section title="用量与疗程" text={data.dosage_course_usage} />
      <Section title="配伍" text={data.couplet} />
      <Section title="临床案例" text={data.clinical_case} />
      <Section title="相关文献" text={data.related_literature} />
    </div>
  );
}
