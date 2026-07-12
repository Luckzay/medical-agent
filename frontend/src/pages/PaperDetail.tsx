import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Typography, Button, Spin, Tag } from 'antd';
import { ArrowLeftOutlined, LinkOutlined } from '@ant-design/icons';
import type { PaperDetail } from '../types';
import { getPaperDetail } from '../services/api';
import styles from './DetailPage.module.css';

const { Title } = Typography;

export default function PaperDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<PaperDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getPaperDetail(Number(id)).then((res) => setData(res.data.data)).finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className={styles.spinWrap}><Spin size="large" /></div>;
  if (!data) return <div className={styles.spinWrap}>未找到该文献</div>;

  return (
    <div>
      <Button icon={<ArrowLeftOutlined />} type="text" onClick={() => navigate(-1)} className={styles.backBtn}>
        返回
      </Button>
      <Title level={3} className={styles.pageTitle}>{data.title}</Title>

      <div style={{ marginBottom: 20 }}>
        <div style={{ color: '#8c8c8c', fontSize: 14 }}>{data.authors}</div>
        <div style={{ color: '#8c8c8c', fontSize: 13, marginTop: 4 }}>
          {data.journal} &middot; {data.year}
        </div>
        <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          {data.tags?.map((t, i) => <Tag key={i}>{t.tag}</Tag>)}
          {data.source_db && <Tag color="default">{data.source_db}</Tag>}
          {data.doi && (
            <a href={`https://doi.org/${data.doi}`} target="_blank" rel="noopener noreferrer">
              <LinkOutlined /> DOI: {data.doi}
            </a>
          )}
        </div>
      </div>

      {data.abstract && (
        <div style={{ marginBottom: 20, borderBottom: '1px solid #f0f0f0', paddingBottom: 16 }}>
          <div style={{ fontWeight: 600, color: '#1a1a1a', marginBottom: 6 }}>摘要</div>
          <div style={{ color: '#333', lineHeight: 1.8, whiteSpace: 'pre-wrap' }}>{data.abstract}</div>
        </div>
      )}
    </div>
  );
}
