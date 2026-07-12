import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Typography, Descriptions, Button, Spin } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import type { MolecularInfo } from '../types';
import { getCompoundDetail } from '../services/api';
import Section from '../components/Section';
import styles from './DetailPage.module.css';

const { Title } = Typography;

export default function CompoundDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<MolecularInfo | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getCompoundDetail(Number(id)).then((res) => setData(res.data.data)).finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className={styles.spinWrap}><Spin size="large" /></div>;
  if (!data) return <div className={styles.spinWrap}>未找到该化合物</div>;

  return (
    <div>
      <Button icon={<ArrowLeftOutlined />} type="text" onClick={() => navigate(-1)} className={styles.backBtn}>
        返回
      </Button>
      <Title level={3} className={styles.pageTitle}>{data.record_title || `化合物 #${data.record_number}`}</Title>

      <Descriptions bordered column={{ xs: 1, sm: 2 }} size="small" className={styles.descriptions}
        labelStyle={{ background: '#fafafa', fontWeight: 600 }}>
        <Descriptions.Item label="Record Number">{data.record_number}</Descriptions.Item>
        <Descriptions.Item label="分子式">{data.molecular_formula || '-'}</Descriptions.Item>
        <Descriptions.Item label="分子量">{data.molecular_weight?.toFixed(2) || '-'}</Descriptions.Item>
        <Descriptions.Item label="XLogP3">{data.xlogp3?.toFixed(2) ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="氢键供体数">{data.hydrogen_bond_donor_count ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="氢键受体数">{data.hydrogen_bond_acceptor_count ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="可旋转键数">{data.rotatable_bond_count ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="重原子数">{data.heavy_atom_count ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="SMILES" span={2}>{data.smiles || '-'}</Descriptions.Item>
        <Descriptions.Item label="InChI" span={2}>
          <div style={{ wordBreak: 'break-all', fontSize: 12 }}>{data.inchi || '-'}</div>
        </Descriptions.Item>
        <Descriptions.Item label="InChI Key" span={2}>
          <div style={{ wordBreak: 'break-all', fontSize: 12 }}>{data.inchi_key || '-'}</div>
        </Descriptions.Item>
      </Descriptions>

      <Section title="记录描述" text={data.record_description} />
      <Section title="FDA 药理学综述" text={data.fda_pharmacology_summary} />
      <Section title="LiverTox 摘要" text={data.livertox_summary} />
    </div>
  );
}
