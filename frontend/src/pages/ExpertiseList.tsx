import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Table, Input, Button, Typography, Popconfirm, message, Modal, Form, InputNumber } from 'antd';
import { SearchOutlined, ReloadOutlined, PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import type { Expertise } from '../types';
import { listExpertises, createExpertise, updateExpertise, deleteExpertise } from '../services/api';
import { useAuth } from '../hooks/useAuth';
import styles from './ListPage.module.css';

const { Title } = Typography;

export default function ExpertiseList() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<Expertise[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState(searchParams.get('keyword') || '');
  const [page, setPage] = useState(Number(searchParams.get('page')) || 1);
  const pageSize = 20;
  const [modalOpen, setModalOpen] = useState(false);
  const [editingRecord, setEditingRecord] = useState<Expertise | null>(null);
  const [form] = Form.useForm();

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

  const handleAdd = () => {
    setEditingRecord(null);
    form.resetFields();
    setModalOpen(true);
  };

  const handleEdit = (record: Expertise) => {
    setEditingRecord(record);
    form.setFieldsValue(record);
    setModalOpen(true);
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteExpertise(id);
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
        await updateExpertise(editingRecord.id, values);
        message.success('更新成功');
      } else {
        await createExpertise(values);
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
    { title: '作者', dataIndex: 'author', key: 'author', width: 120 },
    { title: '文章', dataIndex: 'related_article', key: 'title',
      render: (t: string, r: Expertise) => <a onClick={() => navigate(`/expertises/${r.id}`)}>{t || '查看详情'}</a> },
    { title: '摘要', dataIndex: 'abstract', key: 'abstract', ellipsis: true },
      ...(isAdmin ? [{
        title: '操作', key: 'action', width: 160, fixed: 'right' as const,
        render: (_: any, record: Expertise) => (
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
      <Title level={3} className={styles.pageTitle}>专家经验</Title>
      <div className={styles.searchBar}>
        <Input placeholder="搜索作者、文章、摘要..." value={keyword}
          onChange={(e) => setKeyword(e.target.value)} onPressEnter={onSearch}
          style={{ maxWidth: 320 }} prefix={<SearchOutlined />} allowClear />
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
        onRow={(r) => ({ onClick: () => navigate(`/expertises/${r.id}`), style: { cursor: 'pointer' } })} />

      <Modal title={editingRecord ? '编辑专家经验' : '新增专家经验'} open={modalOpen}
        onOk={handleSubmit} onCancel={() => setModalOpen(false)} width={760} destroyOnHidden>
        <Form form={form} layout="vertical">
          <Form.Item name="herb_id" label="关联药物 ID" rules={[{ required: true, message: '请输入关联药物 ID' }]}>
            <InputNumber style={{ width: '100%' }} min={1} />
          </Form.Item>
          <Form.Item name="author" label="作者">
            <Input />
          </Form.Item>
          <Form.Item name="related_article" label="相关文章">
            <Input />
          </Form.Item>
          <Form.Item name="link_article" label="文章链接">
            <Input />
          </Form.Item>
          <Form.Item name="abstract" label="摘要">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="herb_or_decoction" label="药物或方剂">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="application_situation" label="应用情况">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="dosage_course_usage" label="剂量疗程用法">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="couplet" label="药对">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="clinical_case" label="临床案例">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="related_literature" label="相关文献">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
