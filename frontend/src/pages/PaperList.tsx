import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Table, Input, Button, Typography, Tag, Popconfirm, message, Modal, Form, InputNumber } from 'antd';
import { SearchOutlined, ReloadOutlined, PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import type { Paper } from '../types';
import { listPapers, createPaper, updatePaper, deletePaper } from '../services/api';
import { useAuth } from '../hooks/useAuth';
import styles from './ListPage.module.css';

const { Title } = Typography;

export default function PaperList() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<Paper[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState(searchParams.get('keyword') || '');
  const [page, setPage] = useState(Number(searchParams.get('page')) || 1);
  const pageSize = 20;
  const [modalOpen, setModalOpen] = useState(false);
  const [editingRecord, setEditingRecord] = useState<Paper | null>(null);
  const [form] = Form.useForm();

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

  const handleAdd = () => {
    setEditingRecord(null);
    form.resetFields();
    setModalOpen(true);
  };

  const handleEdit = (record: Paper) => {
    setEditingRecord(record);
    form.setFieldsValue(record);
    setModalOpen(true);
  };

  const handleDelete = async (id: number) => {
    try {
      await deletePaper(id);
      message.success('删除成功');
      fetchData(page, keyword);
    } catch (e: any) {
      message.error(e.response?.data?.error || '删除失败');
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editingRecord) {
        await updatePaper(editingRecord.id, values);
        message.success('更新成功');
      } else {
        await createPaper(values);
        message.success('创建成功');
      }
      setModalOpen(false);
      fetchData(page, keyword);
    } catch (e: any) {
      message.error(e.response?.data?.error || '操作失败');
    }
  };

  const columns = [
    { title: '编号', dataIndex: 'id', key: 'id', width: 80 },
    { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true,
      render: (t: string, r: Paper) => <a onClick={() => navigate(`/papers/${r.id}`)}>{t}</a> },
    { title: '作者', dataIndex: 'authors', key: 'authors', width: 150, ellipsis: true },
    { title: '期刊', dataIndex: 'journal', key: 'journal', width: 140, ellipsis: true },
    { title: '年份', dataIndex: 'year', key: 'year', width: 70 },
    { title: '来源', dataIndex: 'source_db', key: 'source', width: 100,
      render: (v: string) => v ? <Tag>{v}</Tag> : null },
      ...(isAdmin ? [{
        title: '操作', key: 'action', width: 160, fixed: 'right' as const,
        render: (_: any, record: Paper) => (
          <>
            <Button type="link" size="small" icon={<EditOutlined />} onClick={(e) => { e.stopPropagation(); handleEdit(record); }}>编辑</Button>
            <Popconfirm title="确定删除？" onConfirm={(e) => { e?.stopPropagation(); handleDelete(record.id); }} onCancel={(e) => e?.stopPropagation()}>
              <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={(e) => e.stopPropagation()}>删除</Button>
            </Popconfirm>
          </>
        ),
      }] : []),
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
          {isAdmin && (
            <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd} style={{ marginLeft: 'auto' }}>
              新增
            </Button>
          )}
      </div>
      <Table columns={columns} dataSource={data} rowKey="id" loading={loading}
        pagination={{ current: page, total, pageSize, onChange: (p) => { setPage(p); setSearchParams({ keyword, page: String(p) }); }, showTotal: (t) => `共 ${t} 条` }}
        onRow={(r) => ({ onClick: () => navigate(`/papers/${r.id}`), style: { cursor: 'pointer' } })} />

      <Modal title={editingRecord ? '编辑文献' : '新增文献'} open={modalOpen}
        onOk={handleSubmit} onCancel={() => setModalOpen(false)} width={760} destroyOnHidden>
        <Form form={form} layout="vertical">
          <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入标题' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="authors" label="作者">
            <Input />
          </Form.Item>
          <Form.Item name="journal" label="期刊">
            <Input />
          </Form.Item>
          <Form.Item name="year" label="年份">
            <InputNumber style={{ width: '100%' }} min={0} max={3000} />
          </Form.Item>
          <Form.Item name="doi" label="DOI">
            <Input />
          </Form.Item>
          <Form.Item name="source_db" label="来源数据库">
            <Input />
          </Form.Item>
          <Form.Item name="abstract" label="摘要">
            <Input.TextArea rows={5} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
