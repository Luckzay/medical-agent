import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Table, Input, Button, Typography, Tag } from 'antd';
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import type { Paper } from '../types';
import { listPapers } from '../services/api';
import styles from './ListPage.module.css';

const { Title } = Typography;

export default function PaperList() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<Paper[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState(searchParams.get('keyword') || '');
  const [page, setPage] = useState(Number(searchParams.get('page')) || 1);
  const pageSize = 20;

  const fetchData = async (p: number, kw: string) => {
    setLoading(true);
    try {
      const res = await listPapers(p, pageSize, kw);
      setData(res.data.data);
      setTotal(res.data.total);
    } finally { setLoading(false); }
  };

  useEffect(() => { fetchData(page, keyword); }, [page, keyword]);
  const onSearch = () => { setPage(1); setSearchParams({ keyword, page: '1' }); };
  const onReset = () => { setKeyword(''); setPage(1); setSearchParams({}); };

  const columns = [
    { title: '编号', dataIndex: 'id', key: 'id', width: 80 },
    { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true,
      render: (t: string, r: Paper) => <a onClick={() => navigate(`/papers/${r.id}`)}>{t}</a> },
    { title: '作者', dataIndex: 'authors', key: 'authors', width: 150, ellipsis: true },
    { title: '期刊', dataIndex: 'journal', key: 'journal', width: 140, ellipsis: true },
    { title: '年份', dataIndex: 'year', key: 'year', width: 70 },
    { title: '来源', dataIndex: 'source_db', key: 'source', width: 100,
      render: (v: string) => v ? <Tag>{v}</Tag> : null },
  ];

  return (
    <div>
      <Title level={3} className={styles.pageTitle}>文献证据</Title>
      <div className={styles.searchBar}>
        <Input placeholder="搜索标题、作者、期刊、摘要..." value={keyword}
          onChange={(e) => setKeyword(e.target.value)} onPressEnter={onSearch}
          style={{ maxWidth: 400 }} prefix={<SearchOutlined />} allowClear />
        <Button type="primary" onClick={onSearch}>搜索</Button>
        <Button icon={<ReloadOutlined />} onClick={onReset}>重置</Button>
      </div>
      <Table columns={columns} dataSource={data} rowKey="id" loading={loading}
        pagination={{ current: page, total, pageSize, onChange: (p) => { setPage(p); setSearchParams({ keyword, page: String(p) }); }, showTotal: (t) => `共 ${t} 条` }}
        onRow={(r) => ({ onClick: () => navigate(`/papers/${r.id}`), style: { cursor: 'pointer' } })} />
    </div>
  );
}
