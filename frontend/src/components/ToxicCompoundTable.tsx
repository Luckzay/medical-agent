import { Table, Tag, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
import styles from '../pages/DetailPage.module.css';

const { Title } = Typography;

interface CompoundRecord {
  id: number;
  record_number?: number | null;
  compound_name: string;
  compound_type: string;
  molecular_formula: string;
  cas: string;
}

interface ToxicCompoundTableProps {
  compounds: CompoundRecord[];
}

function isToxicCompound(recordNumber?: number | null) {
  return typeof recordNumber === 'number' && recordNumber > 0;
}

export default function ToxicCompoundTable({ compounds }: ToxicCompoundTableProps) {
  const navigate = useNavigate();

  return (
    <div className={styles.subSection}>
      <Title level={4} className={styles.subTitle}>关联化合物</Title>
      <Table
        columns={[
          { title: '化合物名称', dataIndex: 'compound_name', key: 'name' },
          {
            title: '毒性',
            dataIndex: 'record_number',
            key: 'toxicity',
            width: 100,
            render: (recordNumber: number | null | undefined) => (
              isToxicCompound(recordNumber)
                ? <Tag color="error">有毒</Tag>
                : <Tag>无毒</Tag>
            ),
          },
          { title: '类型', dataIndex: 'compound_type', key: 'type', width: 120 },
          { title: '分子式', dataIndex: 'molecular_formula', key: 'formula', width: 160 },
          { title: 'CAS', dataIndex: 'cas', key: 'cas', width: 140 },
          {
            title: '操作',
            key: 'action',
            width: 80,
            render: (_: unknown, record: CompoundRecord) => (
              isToxicCompound(record.record_number)
                ? <a onClick={() => navigate(`/compounds/${record.record_number}`)}>详情</a>
                : <span>-</span>
            ),
          },
        ]}
        dataSource={compounds}
        rowKey="id"
        pagination={false}
        size="small"
        scroll={{ x: 740 }}
        className={styles.subTable}
      />
    </div>
  );
}
