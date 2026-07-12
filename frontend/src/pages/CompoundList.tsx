import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Table, Input, Button, Typography } from 'antd';
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import type { MolecularInfo } from '../types';
import { listCompounds } from '../services/api';
import styles from './ListPage.module.css';

const { Title } = Typography;

export default function CompoundList() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<MolecularInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState(searchParams.get('keyword') || '');
  const [page, setPage] = useState(Number(searchParams.get('page')) || 1);
  const pageSize = 20;

  const fetchData = async (p: number, kw: string) => {
    setLoading(true);
    try {
      const res = await listCompounds(p, pageSize, kw);
      setData(res.data.data);
      setTotal(res.data.total);
    } finally { setLoading(false); }
  };

  useEffect(() => { fetchData(page, keyword); }, [page, keyword]);
  const onSearch = () => { setPage(1); setSearchParams({ keyword, page: '1' }); };
  const onReset = () => { setKeyword(''); setPage(1); setSearchParams({}); };

  const columns = [
    { title: 'Record#', dataIndex: 'record_number', key: 'rn', width: 100 },
    { title: '标题', dataIndex: 'record_title', key: 'title',
      render: (t: string, r: MolecularInfo) => <a onClick={() => navigate(`/compounds/${r.record_number}`)}>{t}</a> },
    { title: '分子式', dataIndex: 'molecular_formula', key: 'formula', width: 160 },
    { title: '分子量', dataIndex: 'molecular_weight', key: 'mw', width: 100, render: (v: number) => v?.toFixed(2) },
    { title: 'InChI Key', dataIndex: 'inchi_key', key: 'inchikey', width: 200, ellipsis: true },
  ];

  return (
    <div>
      <Title level={3} className={styles.pageTitle}>毒性化合物</Title>
      <div className={styles.searchBar}>
        <Input placeholder="搜索标题、分子式、InChI Key、SMILES..." value={keyword}
          onChange={(e) => setKeyword(e.target.value)} onPressEnter={onSearch}
          style={{ maxWidth: 400 }} prefix={<SearchOutlined />} allowClear />
        <Button type="primary" onClick={onSearch}>搜索</Button>
        <Button icon={<ReloadOutlined />} onClick={onReset}>重置</Button>
      </div>
      <Table columns={columns} dataSource={data} rowKey="record_number" loading={loading}
        pagination={{ current: page, total, pageSize, onChange: (p) => { setPage(p); setSearchParams({ keyword, page: String(p) }); }, showTotal: (t) => `共 ${t} 条` }}
        onRow={(r) => ({ onClick: () => navigate(`/compounds/${r.record_number}`), style: { cursor: 'pointer' } })} />
    </div>
  );
}
