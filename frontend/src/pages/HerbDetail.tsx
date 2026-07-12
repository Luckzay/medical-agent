import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Typography, Descriptions, Table, Button, Spin, Tag } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import type { HerbDetail } from '../types';
import { getHerbDetail } from '../services/api';
import Section from '../components/Section';
import styles from './DetailPage.module.css';

const { Title } = Typography;

export default function HerbDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<HerbDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getHerbDetail(Number(id))
      .then((res) => setData(res.data.data))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className={styles.spinWrap}><Spin size="large" /></div>;
  if (!data) return <div className={styles.spinWrap}>未找到该药物</div>;

  const toxicCols = [
    { title: '化合物名称', dataIndex: 'compound_name', key: 'name' },
    { title: '类型', dataIndex: 'compound_type', key: 'type', width: 120 },
    { title: '分子式', dataIndex: 'molecular_formula', key: 'formula', width: 160 },
    { title: 'CAS', dataIndex: 'cas', key: 'cas', width: 140 },
    { title: '操作', key: 'action', width: 100,
      render: (_: any, r: any) => (
        <a onClick={() => navigate(`/compounds/${r.record_number}`)}>详情</a>
      ),
    },
  ];

  const expertiseCols = [
    { title: '作者', dataIndex: 'author', key: 'author', width: 120 },
    { title: '标题', dataIndex: 'related_article', key: 'title', ellipsis: true },
    { title: '摘要', dataIndex: 'abstract', key: 'abstract', ellipsis: true },
    { title: '操作', key: 'action', width: 100,
      render: (_: any, r: any) => <a onClick={() => navigate(`/expertises/${r.id}`)}>详情</a> },
  ];

  return (
    <div>
      <Button icon={<ArrowLeftOutlined />} type="text" onClick={() => navigate(-1)} className={styles.backBtn}>
        返回
      </Button>
      <Title level={3} className={styles.pageTitle}>{data.herb_name}</Title>

      <Descriptions bordered column={1} size="small" className={styles.descriptions}
        labelStyle={{ background: '#fafafa', fontWeight: 600, width: 140 }}>
        <Descriptions.Item label="拼音">{data.herb_name_pinyin}</Descriptions.Item>
        <Descriptions.Item label="毒性">
          {data.virulence && <Tag color="error" className={styles.virulenceTag}>{data.virulence}</Tag>}
        </Descriptions.Item>
      </Descriptions>

      <Section title="药效" text={data.functionality} basis={data.functionality_basis} link={data.link_to_functionality_basis} />
      <Section title="用法用量" text={data.usage_and_dosage} basis={data.basis_for_usage_and_dosage} link={data.link_to_usage_and_dosage} />
      <Section title="毒理机制" text={data.toxicity_mechanism} />
      <Section title="病理检查" text={data.pathological_examination} />
      <Section title="人群禁忌" text={data.crowd_taboo} />
      <Section title="症状禁忌" text={data.symptom_contraindications} />
      <Section title="不良反应 (ADR)" text={data.adr} />
      <Section title="ADR典型案例" text={data.typical_cases_of_adr} />
      <Section title="临床建议" text={data.clinical_suggestion} basis={data.clinical_suggestion_basis} link={data.link_to_clinical_suggestion} />

      <div className={styles.subSection}>
        <Title level={4} className={styles.subTitle}>关联毒性化合物</Title>
        <Table columns={toxicCols} dataSource={data.toxic_compounds} rowKey="id"
          pagination={false} size="small" className={styles.subTable} />
      </div>

      <div className={styles.subSection}>
        <Title level={4} className={styles.subTitle}>关联专家经验</Title>
        <Table columns={expertiseCols} dataSource={data.expertises} rowKey="id"
          pagination={false} size="small" className={styles.subTable} />
      </div>
    </div>
  );
}
