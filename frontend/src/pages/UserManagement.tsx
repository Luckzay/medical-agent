import { useEffect, useState } from 'react';
import { Button, Checkbox, Form, Input, message, Modal, Popconfirm, Select, Space, Table, Tag, Typography } from 'antd';
import { CheckOutlined, CloseOutlined, DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons';
import type { User, UserStatus } from '../types';
import { createUser, deleteUser, getApiErrorMessage, listUsers, updateUser, updateUserStatus } from '../services/api';

const { Title } = Typography;

const statusMeta: Record<UserStatus, { label: string; color: string }> = {
  pending: { label: '待审核', color: 'gold' },
  active: { label: '已通过', color: 'green' },
  rejected: { label: '已拒绝', color: 'red' },
};

export default function UserManagement() {
  const [data, setData] = useState<User[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [reviewingId, setReviewingId] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<Partial<User> | null>(null);
  const [form] = Form.useForm();
  const pageSize = 20;

  const fetchData = async (currentPage: number) => {
    setLoading(true);
    try {
      const response = await listUsers(currentPage, pageSize);
      setData(response.data.data);
      setTotal(response.data.total);
    } finally { setLoading(false); }
  };

  useEffect(() => { fetchData(page); }, [page]);

  const openCreate = () => {
    setEditingUser(null);
    form.resetFields();
    form.setFieldsValue({ role: 'user', gender: 'other', email_consent: false });
    setModalOpen(true);
  };

  const openEdit = (user: User) => {
    setEditingUser(user);
    form.setFieldsValue({ ...user, password: '' });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editingUser?.id) {
        await updateUser(editingUser.id, values);
        message.success('更新成功');
      } else {
        await createUser(values);
        message.success('创建成功');
      }
      setModalOpen(false);
      fetchData(page);
    } catch {
      // Form validation and API errors are handled without closing the modal.
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteUser(id);
      message.success('删除成功');
      fetchData(page);
    } catch {
      message.error('删除失败');
    }
  };

  const handleStatusChange = async (id: number, status: UserStatus) => {
    setReviewingId(id);
    try {
      await updateUserStatus(id, status);
      message.success(status === 'active' ? '已通过审核' : '已拒绝该用户');
      await fetchData(page);
    } catch (error: unknown) {
      message.error(getApiErrorMessage(error, '审核操作失败'));
    } finally {
      setReviewingId(null);
    }
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '用户名', dataIndex: 'username', key: 'username', width: 120 },
    { title: '姓名', dataIndex: 'full_name', key: 'full_name', width: 100 },
    { title: '单位', dataIndex: 'affiliation', key: 'affiliation', width: 180, ellipsis: true },
    { title: '职称', dataIndex: 'professional_title', key: 'professional_title', width: 120, ellipsis: true },
    { title: '邮箱', dataIndex: 'email', key: 'email', width: 180, ellipsis: true },
    { title: '邮件触达', dataIndex: 'email_consent', key: 'email_consent', width: 90,
      render: (consent: boolean) => consent ? <Tag color="green">已同意</Tag> : <Tag>未同意</Tag> },
    { title: '电话', dataIndex: 'phone', key: 'phone', width: 130 },
    { title: '性别', dataIndex: 'gender', key: 'gender', width: 60,
      render: (gender: string) => ({ male: '男', female: '女', other: '其他' }[gender] || gender) },
    { title: '角色', dataIndex: 'role', key: 'role', width: 80,
      render: (role: string) => role === 'admin' ? <Tag color="default">管理员</Tag> : <Tag>用户</Tag> },
    { title: '审核状态', dataIndex: 'status', key: 'status', width: 90,
      render: (status: UserStatus) => {
        const meta = statusMeta[status] || { label: status || '未知', color: 'default' };
        return <Tag color={meta.color}>{meta.label}</Tag>;
      } },
    { title: '操作', key: 'action', width: 280, fixed: 'right' as const,
      render: (_: unknown, user: User) => (
        <Space size={0}>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(user)}>编辑</Button>
          <Button
            type="link"
            size="small"
            icon={<CheckOutlined />}
            disabled={user.status === 'active'}
            loading={reviewingId === user.id}
            onClick={() => handleStatusChange(user.id, 'active')}
          >
            通过
          </Button>
          <Popconfirm title="确定拒绝该用户？" onConfirm={() => handleStatusChange(user.id, 'rejected')}>
            <Button
              type="link"
              size="small"
              danger
              icon={<CloseOutlined />}
              disabled={user.status === 'rejected'}
              loading={reviewingId === user.id}
            >
              拒绝
            </Button>
          </Popconfirm>
          <Popconfirm title="确定删除该用户?" onConfirm={() => handleDelete(user.id)}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={3} style={{ color: '#1a1a1a', margin: 0 }}>用户管理</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建用户</Button>
      </div>
      <Table columns={columns} dataSource={data} rowKey="id" loading={loading}
        scroll={{ x: 1420 }}
        pagination={{ current: page, total, pageSize, onChange: setPage, showTotal: (count) => `共 ${count} 条` }} />

      <Modal title={editingUser ? '编辑用户' : '新建用户'} open={modalOpen}
        onOk={handleSubmit} onCancel={() => setModalOpen(false)} destroyOnHidden>
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="username" label="用户名" rules={[{ required: true }]}>
            <Input disabled={!!editingUser} />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={editingUser ? [] : [{ required: true, message: '请输入密码' }]}>
            <Input.Password placeholder={editingUser ? '留空则不修改' : ''} />
          </Form.Item>
          <Form.Item name="full_name" label="姓名" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="affiliation" label="单位" rules={[{ required: true, whitespace: true, message: '请输入单位' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="professional_title" label="职称" rules={[{ required: true, whitespace: true, message: '请输入职称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="email" label="邮箱" rules={[{ required: true, type: 'email' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="phone" label="电话">
            <Input />
          </Form.Item>
          <Form.Item name="gender" label="性别">
            <Select options={[
              { value: 'male', label: '男' },
              { value: 'female', label: '女' },
              { value: 'other', label: '其他' },
            ]} />
          </Form.Item>
          <Form.Item name="email_consent" valuePropName="checked">
            <Checkbox>同意通过邮箱接收相关产品推送以及专家共识制定邀请</Checkbox>
          </Form.Item>
          <Form.Item name="role" label="角色" rules={[{ required: true }]}>
            <Select options={[
              { value: 'user', label: '普通用户' },
              { value: 'admin', label: '管理员' },
            ]} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
