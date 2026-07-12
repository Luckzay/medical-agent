import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Typography, Descriptions, Table, Button, Spin, Tag } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import type { DecoctionDetail } from '../types';
import { getDecoctionDetail } from '../services/api';
import Section from '../components/Section';
import styles from './DetailPage.module.css';

const { Title } = Typography;

export default function DecoctionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<DecoctionDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getDecoctionDetail(Number(id)).then((res) => setData(res.data.data)).finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className={styles.spinWrap}><Spin size="large" /></div>;
  if (!data) return <div className={styles.spinWrap}>未找到该方剂</div>;

  const metaCols = [
    { title: 'Review', dataIndex: 'review_number', key: 'review', width: 80 },
    { title: '指标', dataIndex: 'index_value', key: 'index', width: 120 },
    { title: '研究', dataIndex: 'study', key: 'study', width: 160, ellipsis: true },
    { title: 'OR/RR', dataIndex: 'or_or_rr', key: 'or', width: 80, render: (v: number) => v?.toFixed(2) },
    { title: '95%CI Lower', dataIndex: 'ci_95_lower', key: 'ci_l', width: 110, render: (v: number) => v?.toFixed(2) },
    { title: '95%CI Upper', dataIndex: 'ci_95_upper', key: 'ci_u', width: 110, render: (v: number) => v?.toFixed(2) },
    { title: 'P值', dataIndex: 'p_value', key: 'p', width: 70, render: (v: number) => v?.toFixed(3) },
    { title: 'I²', dataIndex: 'i2', key: 'i2', width: 70 },
    { title: '模型', dataIndex: 'model', key: 'model', width: 80 },
  ];

  return (
    <div>
      <Button icon={<ArrowLeftOutlined />} type="text" onClick={() => navigate(-1)} className={styles.backBtn}>
        返回
      </Button>
      <Title level={3} className={styles.pageTitle}>{data.decoction_name}</Title>

      <Descriptions bordered column={1} size="small" className={styles.descriptions}
        labelStyle={{ background: '#fafafa', fontWeight: 600, width: 140 }}>
        <Descriptions.Item label="拼音">{data.decoction_name_pinyin}</Descriptions.Item>
        <Descriptions.Item label="剂型">{data.dosage_form}</Descriptions.Item>
        <Descriptions.Item label="毒性">
          {data.virulence && <Tag color="error" className={styles.virulenceTag}>{data.virulence}</Tag>}
        </Descriptions.Item>
      </Descriptions>

      <Section title="功效" text={data.functionality} basis={data.functionality_basis} link={data.link_to_functionality_basis} />
      <Section title="用法用量" text={data.usage_and_dosage} basis={data.basis_for_usage_and_dosage} link={data.link_to_usage_and_dosage} />
      <Section title="毒理机制" text={data.toxicity_mechanism} />
      <Section title="病理检查" text={data.pathological_examination} />
      <Section title="人群禁忌" text={data.crowd_taboo} />
      <Section title="症状禁忌" text={data.symptom_contraindications} />
      <Section title="关联毒性中药" text={data.related_toxic_herbs} />
      <Section title="不良反应 (ADR)" text={data.adr} />
      <Section title="ADR典型案例" text={data.typical_cases_of_adr} />
      <Section title="临床建议" text={data.clinical_suggestion} basis={data.clinical_suggestion_basis} link={data.link_to_clinical_suggestion} />
      <Section title="相关研究" text={data.related_studies} link={data.link_to_related_studies} />
      <Section title="相关研究结论" text={data.conclusion_of_related_studies} />

      <div className={styles.subSection}>
        <Title level={4} className={styles.subTitle}>Meta 分析数据</Title>
        <Table columns={metaCols} dataSource={data.meta} rowKey="id"
          pagination={false} size="small" scroll={{ x: 800 }} className={styles.subTable} />
      </div>
      <div className={styles.subSection}>
        <Title level={4} className={styles.subTitle}>关联化合物</Title>
        <Table columns={[
          { title: '名称', dataIndex: 'compound_name', key: 'name' },
          { title: '类型', dataIndex: 'compound_type', key: 'type', width: 120 },
          { title: '分子式', dataIndex: 'molecular_formula', key: 'formula', width: 160 },
          { title: 'CAS', dataIndex: 'cas', key: 'cas', width: 140 },
        ]} dataSource={data.compounds} rowKey="id" pagination={false} size="small" className={styles.subTable} />
      </div>
      <div className={styles.subSection}>
        <Title level={4} className={styles.subTitle}>关联毒性化合物</Title>
        <Table columns={[
          { title: '名称', dataIndex: 'compound_name', key: 'name' },
          { title: '类型', dataIndex: 'compound_type', key: 'type', width: 120 },
          { title: '分子式', dataIndex: 'molecular_formula', key: 'formula', width: 160 },
          { title: 'CAS', dataIndex: 'cas', key: 'cas', width: 140 },
          { title: '操作', key: 'action', width: 80,
            render: (_: any, r: any) => <a onClick={() => navigate(`/compounds/${r.record_number}`)}>详情</a> },
        ]} dataSource={data.toxic_compounds} rowKey="id" pagination={false} size="small" className={styles.subTable} />
      </div>
    </div>
  );
}
