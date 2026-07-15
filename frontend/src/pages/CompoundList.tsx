import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Table, Input, Button, Typography, Popconfirm, message, Modal, Form, InputNumber } from 'antd';
import { SearchOutlined, ReloadOutlined, PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import type { MolecularInfo } from '../types';
import { listCompounds, createCompound, updateCompound, deleteCompound } from '../services/api';
import { useAuth } from '../hooks/useAuth';
import styles from './ListPage.module.css';

const { Title } = Typography;

export default function CompoundList() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<MolecularInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState(searchParams.get('keyword') || '');
  const [page, setPage] = useState(Number(searchParams.get('page')) || 1);
  const pageSize = 20;
  const [modalOpen, setModalOpen] = useState(false);
  const [editingRecord, setEditingRecord] = useState<MolecularInfo | null>(null);
  const [form] = Form.useForm();

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

  const handleAdd = () => {
    setEditingRecord(null);
    form.resetFields();
    setModalOpen(true);
  };

  const handleEdit = (record: MolecularInfo) => {
    setEditingRecord(record);
    form.setFieldsValue(record);
    setModalOpen(true);
  };

  const handleDelete = async (recordNumber: number) => {
    try {
      await deleteCompound(recordNumber);
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
        await updateCompound(editingRecord.record_number, values);
        message.success('更新成功');
      } else {
        await createCompound(values);
        message.success('创建成功');
      }
      setModalOpen(false);
      fetchData(page, keyword);
    } catch (e: any) {
      message.error(e.response?.data?.error || '操作失败');
    }
  };

  const columns = [
    { title: 'Record#', dataIndex: 'record_number', key: 'rn', width: 100 },
    { title: '标题', dataIndex: 'record_title', key: 'title',
      render: (t: string, r: MolecularInfo) => <a onClick={() => navigate(`/compounds/${r.record_number}`)}>{t}</a> },
    { title: '分子式', dataIndex: 'molecular_formula', key: 'formula', width: 160 },
    { title: '分子量', dataIndex: 'molecular_weight', key: 'mw', width: 100, render: (v: number) => v?.toFixed(2) },
    { title: 'InChI Key', dataIndex: 'inchi_key', key: 'inchikey', width: 200, ellipsis: true },
      ...(isAdmin ? [{
        title: '操作', key: 'action', width: 160, fixed: 'right' as const,
        render: (_: any, record: MolecularInfo) => (
          <>
            <Button type="link" size="small" icon={<EditOutlined />} onClick={(e) => { e.stopPropagation(); handleEdit(record); }}>编辑</Button>
            <Popconfirm title="确定删除？" onConfirm={(e) => { e?.stopPropagation(); handleDelete(record.record_number); }} onCancel={(e) => e?.stopPropagation()}>
              <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={(e) => e.stopPropagation()}>删除</Button>
            </Popconfirm>
          </>
        ),
      }] : []),
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
          {isAdmin && (
            <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd} style={{ marginLeft: 'auto' }}>
              新增
            </Button>
          )}
      </div>
      <Table columns={columns} dataSource={data} rowKey="record_number" loading={loading}
        pagination={{ current: page, total, pageSize, onChange: (p) => { setPage(p); setSearchParams({ keyword, page: String(p) }); }, showTotal: (t) => `共 ${t} 条` }}
        onRow={(r) => ({ onClick: () => navigate(`/compounds/${r.record_number}`), style: { cursor: 'pointer' } })} />

      <Modal title={editingRecord ? '编辑化合物' : '新增化合物'} open={modalOpen}
        onOk={handleSubmit} onCancel={() => setModalOpen(false)} width={760} destroyOnHidden>
        <Form form={form} layout="vertical">
          {!editingRecord && (
            <Form.Item name="record_number" label="Record Number">
              <InputNumber style={{ width: '100%' }} />
            </Form.Item>
          )}
          <Form.Item name="record_title" label="标题" rules={[{ required: true, message: '请输入标题' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="molecular_formula" label="分子式">
            <Input />
          </Form.Item>
          <Form.Item name="molecular_weight" label="分子量">
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="xlogp3" label="XLogP3">
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="inchi_key" label="InChI Key">
            <Input />
          </Form.Item>
          <Form.Item name="inchi" label="InChI">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="smiles" label="SMILES">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="record_description" label="记录描述">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="fda_pharmacology_summary" label="FDA 药理学综述">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="livertox_summary" label="LiverTox 摘要">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
