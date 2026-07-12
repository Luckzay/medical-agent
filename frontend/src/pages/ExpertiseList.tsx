import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Table, Input, Button, Typography } from 'antd';
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import type { Expertise } from '../types';
import { listExpertises } from '../services/api';
import styles from './ListPage.module.css';

const { Title } = Typography;

export default function ExpertiseList() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<Expertise[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState(searchParams.get('keyword') || '');
  const [page, setPage] = useState(Number(searchParams.get('page')) || 1);
  const pageSize = 20;

  const fetchData = async (p: number, kw: string) => {
    setLoading(true);
    try {
      const res = await listExpertises(p, pageSize, kw);
      setData(res.data.data);
      setTotal(res.data.total);
    } finally { setLoading(false); }
  };

  useEffect(() => { fetchData(page, keyword); }, [page, keyword]);
  const onSearch = () => { setPage(1); setSearchParams({ keyword, page: '1' }); };
  const onReset = () => { setKeyword(''); setPage(1); setSearchParams({}); };

  const columns = [
    { title: '编号', dataIndex: 'id', key: 'id', width: 80 },
    { title: '作者', dataIndex: 'author', key: 'author', width: 120 },
    { title: '文章', dataIndex: 'related_article', key: 'title',
      render: (t: string, r: Expertise) => <a onClick={() => navigate(`/expertises/${r.id}`)}>{t || '查看详情'}</a> },
    { title: '摘要', dataIndex: 'abstract', key: 'abstract', ellipsis: true },
  ];

  return (
    <div>
      <Title level={3} className={styles.pageTitle}>专家经验</Title>
      <div className={styles.searchBar}>
        <Input placeholder="搜索作者、文章、摘要..." value={keyword}
          onChange={(e) => setKeyword(e.target.value)} onPressEnter={onSearch}
          style={{ maxWidth: 320 }} prefix={<SearchOutlined />} allowClear />
        <Button type="primary" onClick={onSearch}>搜索</Button>
        <Button icon={<ReloadOutlined />} onClick={onReset}>重置</Button>
      </div>
      <Table columns={columns} dataSource={data} rowKey="id" loading={loading}
        pagination={{ current: page, total, pageSize, onChange: (p) => { setPage(p); setSearchParams({ keyword, page: String(p) }); }, showTotal: (t) => `共 ${t} 条` }}
        onRow={(r) => ({ onClick: () => navigate(`/expertises/${r.id}`), style: { cursor: 'pointer' } })} />
    </div>
  );
}
