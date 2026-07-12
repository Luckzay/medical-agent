import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Form, Input, Button, Typography, message, Select } from 'antd';
import { UserOutlined, LockOutlined, MailOutlined, IdcardOutlined, PhoneOutlined } from '@ant-design/icons';
import { register } from '../services/api';

const { Title } = Typography;

export default function RegisterPage() {
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const onFinish = async (values: Record<string, string>) => {
    setLoading(true);
    try {
      await register({
        username: values.username,
        password: values.password,
        full_name: values.full_name,
        phone: values.phone || '',
        gender: values.gender || 'other',
        email: values.email,
      });
      message.success('注册成功，请登录');
      navigate('/login');
    } catch {
      message.error('注册失败，用户名或邮箱可能已存在');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center',
      justifyContent: 'center', background: '#fafafa',
    }}>
      <div style={{
        width: 400, background: '#fff', padding: '40px 32px',
        border: '1px solid #f0f0f0', borderRadius: 4,
      }}>
        <Title level={3} style={{ textAlign: 'center', color: '#1a1a1a', marginBottom: 24 }}>
          用户注册
        </Title>
        <Form onFinish={onFinish} size="large" layout="vertical">
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="登录用户名" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[
            { required: true, message: '请输入密码' },
            { min: 6, message: '密码至少6位' },
          ]}>
            <Input.Password prefix={<LockOutlined />} placeholder="至少6位" />
          </Form.Item>
          <Form.Item name="full_name" label="姓名" rules={[{ required: true, message: '请输入姓名' }]}>
            <Input prefix={<IdcardOutlined />} placeholder="真实姓名" />
          </Form.Item>
          <Form.Item name="email" label="邮箱" rules={[
            { required: true, message: '请输入邮箱' },
            { type: 'email', message: '邮箱格式不正确' },
          ]}>
            <Input prefix={<MailOutlined />} placeholder="example@mail.com" />
          </Form.Item>
          <Form.Item name="phone" label="电话">
            <Input prefix={<PhoneOutlined />} placeholder="手机号（选填）" />
          </Form.Item>
          <Form.Item name="gender" label="性别" initialValue="other">
            <Select options={[
              { value: 'male', label: '男' },
              { value: 'female', label: '女' },
              { value: 'other', label: '其他' },
            ]} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>
              注册
            </Button>
          </Form.Item>
          <div style={{ textAlign: 'center' }}>
            已有账号？<Link to="/login">去登录</Link>
          </div>
        </Form>
      </div>
    </div>
  );
}
