import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button, Descriptions, Spin, Tag, Typography } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import type { DecoctionDetail } from '../types';
import { getDecoctionDetail } from '../services/api';
import Section from '../components/Section';
import ToxicCompoundTable from '../components/ToxicCompoundTable';
import styles from './DetailPage.module.css';

const { Title } = Typography;

export default function DecoctionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<DecoctionDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) {
      return;
    }
    setLoading(true);
    getDecoctionDetail(Number(id)).then((res) => setData(res.data.data)).finally(() => setLoading(false));
  }, [id]);

  if (loading) {return <div className={styles.spinWrap}><Spin size="large" /></div>;}
  if (!data) {return <div className={styles.spinWrap}>未找到该方剂</div>;}

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
          {data.virulence ? <Tag color="error" className={styles.virulenceTag}>{data.virulence}</Tag> : null}
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

      <ToxicCompoundTable compounds={data.toxic_compounds} />
    </div>
  );
}
