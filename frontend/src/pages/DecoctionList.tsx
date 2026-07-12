import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Table, Input, Button, Typography, Popconfirm, message } from 'antd';
import { SearchOutlined, ReloadOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import type { DecoctionBasic } from '../types';
import { listDecoctions, deleteDecoction } from '../services/api';
import { useAuth } from '../hooks/useAuth';
import styles from './ListPage.module.css';

const { Title } = Typography;

export default function DecoctionList() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<DecoctionBasic[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState(searchParams.get('keyword') || '');
  const [page, setPage] = useState(Number(searchParams.get('page')) || 1);
  const pageSize = 20;

  const fetchData = async (p: number, kw: string) => {
    setLoading(true);
    try {
      const res = await listDecoctions(p, pageSize, kw);
      setData(res.data.data);
      setTotal(res.data.total);
    } finally { setLoading(false); }
  };

  useEffect(() => { fetchData(page, keyword); }, [page, keyword]);
  const onSearch = () => { setPage(1); setSearchParams({ keyword, page: '1' }); };
  const onReset = () => { setKeyword(''); setPage(1); setSearchParams({}); };

  const handleDelete = async (id: number) => {
    try {
      await deleteDecoction(id);
      message.success('删除成功');
      fetchData(page, keyword);
    } catch (e: any) {
      message.error(e.response?.data?.error || '删除失败');
    }
  };

  const columns = [
    { title: '编号', dataIndex: 'id', key: 'id', width: 30 },
    { title: '方剂名', dataIndex: 'decoction_name', key: 'name', width: 100,
      render: (t: string, r: DecoctionBasic) => <a onClick={() => navigate(`/decoctions/${r.id}`)}>{t}</a> },
    { title: '拼音', dataIndex: 'decoction_name_pinyin', key: 'pinyin', width: 80 },
    { title: '剂型', dataIndex: 'dosage_form', key: 'form', width: 80 },
    { title: '毒性', dataIndex: 'virulence', key: 'virulence', width: 300,
      render: (v: string) => v ? <span style={{ color: '#cf1322' }}>{v}</span> : '-' },
    ...(isAdmin ? [{
      title: '操作', key: 'action', width: 120, fixed: 'right' as const,
      render: (_: any, record: DecoctionBasic) => (
        <>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={(e) => { e.stopPropagation(); navigate(`/decoctions/${record.id}`); }}>查看</Button>
          <Popconfirm title="确定删除？" onConfirm={(e) => { e?.stopPropagation(); handleDelete(record.id); }} onCancel={(e) => e?.stopPropagation()}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={(e) => e.stopPropagation()}>删除</Button>
          </Popconfirm>
        </>
      ),
    }] : []),
  ];

  return (
    <div>
      <Title level={3} className={styles.pageTitle}>毒性方剂</Title>
      <div className={styles.searchBar}>
        <Input placeholder="搜索方剂名、拼音、毒性..." value={keyword}
          onChange={(e) => setKeyword(e.target.value)} onPressEnter={onSearch}
          style={{ maxWidth: 320 }} prefix={<SearchOutlined />} allowClear />
        <Button type="primary" onClick={onSearch}>搜索</Button>
        <Button icon={<ReloadOutlined />} onClick={onReset}>重置</Button>
      </div>
      <Table columns={columns} dataSource={data} rowKey="id" loading={loading}
        pagination={{ current: page, total, pageSize, onChange: (p) => { setPage(p); setSearchParams({ keyword, page: String(p) }); }, showTotal: (t) => `共 ${t} 条` }}/>
    </div>
  );
}
