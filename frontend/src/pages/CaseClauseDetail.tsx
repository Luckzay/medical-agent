import { useEffect, useState } from 'react';
import { Button, Descriptions, Empty, Spin, Table, Typography, message } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useNavigate, useParams } from 'react-router-dom';
import type { CaseClauseDetail as CaseClauseDetailData, DecoctionBasic, HerbBasic } from '../types';
import { getCaseDetail, getClauseDetail } from '../services/api';
import { getFieldLabel, getRecordTitle, hasDisplayValue, isBusinessField, renderDynamicValue } from '../utils/dynamicRecord';
import Section from '../components/Section';
import styles from './DetailPage.module.css';

const { Title } = Typography;

interface CaseClauseDetailProps {
  kind: 'cases' | 'clauses';
}

const pageConfig = {
  cases: { fallbackTitle: '医案详情', request: getCaseDetail },
  clauses: { fallbackTitle: '条文及论述详情', request: getClauseDetail },
};

const sectionFieldOrder = {
  cases: [
    'main_complaint', 'symptoms_and_history', 'past_history', 'symptom_description',
    'diagnosis', 'syndrome', 'treatment_principle', 'specific_treatment',
    'intervention_method', 'response_to_treatment', 'outcome', 'result',
    'failure_reason', 'explanation_of_ineffectiveness', 'adjustment_for_ineffectiveness',
    'aggravation', 'combined_explanation', 'original_text', 'notes', 'reference',
  ],
  clauses: [
    'target_content', 'original_text', 'clause', 'content', 'discussion', 'analysis',
    'symptom_description', 'intervention_method', 'explanation_of_ineffectiveness',
    'combined_explanation', 'notes', 'reference',
  ],
};

const titleFields = new Set(['case_title', 'clause_title', 'title', 'name']);

function asSectionText(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map((item) => typeof item === 'object' ? JSON.stringify(item) : String(item)).join('、');
  }
  if (typeof value === 'object' && value !== null) {
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}

export default function CaseClauseDetail({ kind }: CaseClauseDetailProps) {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<CaseClauseDetailData | null>(null);
  const [loading, setLoading] = useState(true);
  const config = pageConfig[kind];

  useEffect(() => {
    if (!id) {
      return;
    }
    let active = true;
    setLoading(true);
    config.request(id)
      .then((response) => {
        if (active) {
          setData(response.data.data);
        }
      })
      .catch(() => {
        if (active) {
          message.error(`加载${config.fallbackTitle}失败`);
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [config, id]);

  if (loading) {
    return <div className={styles.spinWrap}><Spin size="large" /></div>;
  }
  if (!data) {
    return <Empty description="未找到相关记录" />;
  }

  const businessFields = Object.entries(data.record)
    .filter(([key, value]) => isBusinessField(key) && hasDisplayValue(value));
  const configuredSections = sectionFieldOrder[kind];
  const sectionKeys = new Set([
    ...configuredSections,
    ...businessFields
      .filter(([, value]) => typeof value === 'string' && value.length > 80)
      .map(([key]) => key),
  ]);
  const descriptionFields = businessFields
    .filter(([key]) => !titleFields.has(key) && !sectionKeys.has(key));
  const sectionFields = businessFields
    .filter(([key]) => sectionKeys.has(key))
    .sort(([a], [b]) => {
      const aIndex = configuredSections.indexOf(a);
      const bIndex = configuredSections.indexOf(b);
      return (aIndex < 0 ? configuredSections.length : aIndex) -
        (bIndex < 0 ? configuredSections.length : bIndex);
    });

  const herbColumns = [
    {
      title: '中药名称',
      dataIndex: 'herb_name',
      key: 'name',
      render: (name: string, record: HerbBasic) => (
        <a onClick={() => navigate(`/herbs/${record.id}`)}>{name || `中药 #${record.id}`}</a>
      ),
    },
    { title: '拼音', dataIndex: 'herb_name_pinyin', key: 'pinyin' },
    { title: '毒性', dataIndex: 'virulence', key: 'virulence', ellipsis: true },
  ];
  const decoctionColumns = [
    {
      title: '方剂名称',
      dataIndex: 'decoction_name',
      key: 'name',
      render: (name: string, record: DecoctionBasic) => (
        <a onClick={() => navigate(`/decoctions/${record.id}`)}>{name || `方剂 #${record.id}`}</a>
      ),
    },
    { title: '剂型', dataIndex: 'dosage_form', key: 'form' },
    { title: '毒性', dataIndex: 'virulence', key: 'virulence', ellipsis: true },
  ];

  return (
    <div>
      <Button icon={<ArrowLeftOutlined />} type="text" onClick={() => navigate(-1)} className={styles.backBtn}>
        返回
      </Button>
      <Title level={3} className={styles.pageTitle}>
        {getRecordTitle(data.record, config.fallbackTitle)}
      </Title>

      {descriptionFields.length > 0 && (
        <Descriptions
          bordered
          column={1}
          size="small"
          className={styles.descriptions}
          labelStyle={{ background: '#fafafa', fontWeight: 600, width: 140 }}
        >
          {descriptionFields.map(([key, value]) => (
            <Descriptions.Item key={key} label={getFieldLabel(key)}>
              {renderDynamicValue(value)}
            </Descriptions.Item>
          ))}
        </Descriptions>
      )}

      {sectionFields.map(([key, value]) => (
        <Section key={key} title={getFieldLabel(key)} text={asSectionText(value)} />
      ))}

      {data.herbs.length > 0 && (
        <div className={styles.subSection}>
          <Title level={4} className={styles.subTitle}>关联中药</Title>
          <Table
            columns={herbColumns}
            dataSource={data.herbs}
            rowKey="id"
            pagination={false}
            size="small"
            scroll={{ x: 520 }}
            onRow={(record) => ({ onClick: () => navigate(`/herbs/${record.id}`), style: { cursor: 'pointer' } })}
          />
        </div>
      )}

      {data.decoctions.length > 0 && (
        <div className={styles.subSection}>
          <Title level={4} className={styles.subTitle}>关联方剂</Title>
          <Table
            columns={decoctionColumns}
            dataSource={data.decoctions}
            rowKey="id"
            pagination={false}
            size="small"
            scroll={{ x: 520 }}
            onRow={(record) => ({ onClick: () => navigate(`/decoctions/${record.id}`), style: { cursor: 'pointer' } })}
          />
        </div>
      )}
    </div>
  );
}
