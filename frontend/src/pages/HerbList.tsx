import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Table, Input, Button, Typography } from 'antd';
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import type { HerbBasic } from '../types';
import { listHerbs } from '../services/api';
import styles from './ListPage.module.css';

const { Title } = Typography;

export default function HerbList() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<HerbBasic[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState(searchParams.get('keyword') || '');
  const [page, setPage] = useState(Number(searchParams.get('page')) || 1);
  const pageSize = 20;

  const fetchData = async (p: number, kw: string) => {
    setLoading(true);
    try {
      const res = await listHerbs(p, pageSize, kw);
      setData(res.data.data);
      setTotal(res.data.total);
    } finally { setLoading(false); }
  };

  useEffect(() => { fetchData(page, keyword); }, [page, keyword]);
  const onSearch = () => { setPage(1); setSearchParams({ keyword, page: '1' }); };
  const onReset = () => { setKeyword(''); setPage(1); setSearchParams({}); };

  const columns = [
    { title: '编号', dataIndex: 'id', key: 'id', width: 80 },
    { title: '名称', dataIndex: 'herb_name', key: 'herb_name',
      render: (t: string, r: HerbBasic) => <a onClick={() => navigate(`/herbs/${r.id}`)}>{t}</a> },
    { title: '拼音', dataIndex: 'herb_name_pinyin', key: 'pinyin', width: 160 },
    { title: '毒性', dataIndex: 'virulence', key: 'virulence', width: 100,
      render: (v: string) => v ? <span style={{ color: '#cf1322' }}>{v}</span> : '-' },
    { title: '用法用量', dataIndex: 'usage_and_dosage', key: 'dosage', ellipsis: true },
  ];

  return (
    <div>
      <Title level={3} className={styles.pageTitle}>毒性中药</Title>
      <div className={styles.searchBar}>
        <Input placeholder="搜索名称、拼音、毒性..." value={keyword}
          onChange={(e) => setKeyword(e.target.value)} onPressEnter={onSearch}
          style={{ maxWidth: 320 }} prefix={<SearchOutlined />} allowClear />
        <Button type="primary" onClick={onSearch}>搜索</Button>
        <Button icon={<ReloadOutlined />} onClick={onReset}>重置</Button>
      </div>
      <Table columns={columns} dataSource={data} rowKey="id" loading={loading}
        pagination={{ current: page, total, pageSize, onChange: (p) => { setPage(p); setSearchParams({ keyword, page: String(p) }); }, showTotal: (t) => `共 ${t} 条` }}
        onRow={(r) => ({ onClick: () => navigate(`/herbs/${r.id}`), style: { cursor: 'pointer' } })} />
    </div>
  );
}
