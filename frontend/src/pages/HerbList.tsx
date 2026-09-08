import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Table, Input, Button, Typography, Popconfirm, message, Modal, Form } from 'antd';
import { SearchOutlined, ReloadOutlined, PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import type { HerbBasic } from '../types';
import { listHerbs, createHerb, updateHerb, deleteHerb } from '../services/api';
import { useAuth } from '../hooks/useAuth';
import GuestListNotice from '../components/GuestListNotice';
import styles from './ListPage.module.css';

const { Title } = Typography;

export default function HerbList() {
  const navigate = useNavigate();
  const { user, isAuthenticated } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<HerbBasic[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState(searchParams.get('keyword') || '');
  const [page, setPage] = useState(Number(searchParams.get('page')) || 1);
  const pageSize = 20;
  const visiblePage = isAuthenticated ? page : 1;
  const [modalOpen, setModalOpen] = useState(false);
  const [editingRecord, setEditingRecord] = useState<HerbBasic | null>(null);
  const [form] = Form.useForm();

  const fetchData = async (p: number, kw: string) => {
    setLoading(true);
    try {
      const res = await listHerbs(p, pageSize, kw);
      setData(res.data.data);
      setTotal(res.data.total);
    } finally { setLoading(false); }
  };

  useEffect(() => { fetchData(visiblePage, keyword); }, [visiblePage, keyword]);
  const onSearch = () => { setPage(1); setSearchParams({ keyword, page: '1' }); };
  const onReset = () => { setKeyword(''); setPage(1); setSearchParams({}); };

  const handleAdd = () => {
    setEditingRecord(null);
    form.resetFields();
    setModalOpen(true);
  };

  const handleEdit = (record: HerbBasic) => {
    setEditingRecord(record);
    form.setFieldsValue(record);
    setModalOpen(true);
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteHerb(id);
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
        await updateHerb(editingRecord.id, values);
        message.success('更新成功');
      } else {
        await createHerb(values);
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
    { title: '名称', dataIndex: 'herb_name', key: 'herb_name',
      render: (t: string, r: HerbBasic) => <a onClick={() => navigate(`/herbs/${r.id}`)}>{t}</a> },
    { title: '拼音', dataIndex: 'herb_name_pinyin', key: 'pinyin', width: 160 },
    { title: '毒性', dataIndex: 'virulence', key: 'virulence', width: 100,
      render: (v: string) => v ? <span style={{ color: '#cf1322' }}>{v}</span> : '-' },
    { title: '用法用量', dataIndex: 'usage_and_dosage', key: 'dosage', ellipsis: true },
    ...(isAdmin ? [{
      title: '操作', key: 'action', width: 160, fixed: 'right' as const,
      render: (_: any, record: HerbBasic) => (
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
      <Title level={3} className={styles.pageTitle}>毒性中药</Title>
      <div className={styles.searchBar}>
        <Input placeholder="搜索名称、拼音、毒性..." value={keyword}
          onChange={(e) => setKeyword(e.target.value)} onPressEnter={onSearch}
          style={{ maxWidth: 320 }} prefix={<SearchOutlined />} allowClear />
        <Button type="primary" onClick={onSearch}>搜索</Button>
        <Button icon={<ReloadOutlined />} onClick={onReset}>重置</Button>
        {isAdmin ? (
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd} style={{ marginLeft: 'auto' }}>
            新增
          </Button>
        ) : null}
      </div>
      <Table columns={columns} dataSource={data} rowKey="id" loading={loading}
        pagination={{ current: visiblePage, total: isAuthenticated ? total : Math.min(total, pageSize), pageSize, hideOnSinglePage: true, onChange: (p) => { setPage(p); setSearchParams({ keyword, page: String(p) }); }, showTotal: (t) => `共 ${t} 条` }}
        onRow={(r) => ({ onClick: () => navigate(`/herbs/${r.id}`), style: { cursor: 'pointer' } })} />
      <GuestListNotice total={total} pageSize={pageSize} />

      <Modal
        title={editingRecord ? '编辑药物' : '新增药物'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        width={600}
          destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="herb_name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="herb_name_pinyin" label="拼音">
            <Input />
          </Form.Item>
          <Form.Item name="virulence" label="毒性">
            <Input />
          </Form.Item>
          <Form.Item name="functionality" label="功能主治">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="usage_and_dosage" label="用法用量">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="toxicity_mechanism" label="毒性机制">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="clinical_suggestion" label="临床建议">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
