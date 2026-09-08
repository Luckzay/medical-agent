import { useEffect, useState } from 'react';
import { Alert, Button, Card, Form, Input, Select, Space, Switch, Tag, Typography, message } from 'antd';
import { KeyOutlined, SaveOutlined } from '@ant-design/icons';
import type { LLMConfig, UpdateLLMConfigRequest } from '../types';
import { getApiErrorMessage, getLLMConfig, updateLLMConfig } from '../services/api';
import styles from './LLMConfigPage.module.css';

const { Title, Paragraph, Text } = Typography;

export default function LLMConfigPage() {
  const [form] = Form.useForm<UpdateLLMConfigRequest>();
  const [config, setConfig] = useState<LLMConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const loadConfig = async () => {
      try {
        const response = await getLLMConfig();
        const value = response.data;
        setConfig(value);
        form.setFieldsValue({
          provider: value.provider,
          base_url: value.base_url,
          api_key: '',
          model_name: value.model_name,
          enabled: value.enabled,
        });
      } catch (error: unknown) {
        message.error(getApiErrorMessage(error, '读取 LLM 配置失败'));
      } finally {
        setLoading(false);
      }
    };
    void loadConfig();
  }, [form]);

  const handleSubmit = async (values: UpdateLLMConfigRequest) => {
    setSaving(true);
    try {
      await updateLLMConfig({ ...values, api_key: values.api_key?.trim() || '' });
      message.success('LLM 配置已保存');
      form.setFieldValue('api_key', '');
      const response = await getLLMConfig();
      setConfig(response.data);
    } catch (error: unknown) {
      message.error(getApiErrorMessage(error, '保存 LLM 配置失败'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.heading}>
        <div>
          <Title level={2}>LLM 配置</Title>
          <Paragraph type="secondary">配置智能研究工作台使用的大语言模型服务，仅管理员可访问。</Paragraph>
        </div>
        <KeyOutlined className={styles.headingIcon} />
      </div>

      <Alert
        type="info"
        showIcon
        message="API Key 安全说明"
        description="系统不会返回或回填完整 API Key。密码框留空时将保留当前密钥，只有输入新值才会替换。"
      />

      <Card loading={loading} className={styles.card}>
        <Form form={form} layout="vertical" onFinish={handleSubmit} requiredMark="optional">
          <div className={styles.grid}>
            <Form.Item name="provider" label="服务提供商" rules={[{ required: true, whitespace: true, message: '请输入服务提供商' }]}>
              <Select
                showSearch
                placeholder="选择或输入提供商"
                options={[
                  { value: 'openai', label: 'OpenAI Compatible' },
                  { value: 'ark', label: '火山方舟' },
                  { value: 'deepseek', label: 'DeepSeek' },
                ]}
              />
            </Form.Item>
            <Form.Item name="model_name" label="模型名称" rules={[{ required: true, whitespace: true, message: '请输入模型名称' }]}>
              <Input placeholder="例如：doubao-pro-32k" />
            </Form.Item>
          </div>

          <Form.Item name="base_url" label="Base URL" rules={[{ required: true, whitespace: true, message: '请输入 Base URL' }, { type: 'url', message: '请输入有效 URL' }]}>
            <Input placeholder="https://example.com/v1" />
          </Form.Item>

          <Form.Item
            name="api_key"
            label={
              <Space wrap>
                <span>API Key</span>
                {config?.has_api_key ? <Tag color="success">已配置 {config.masked_api_key}</Tag> : <Tag>未配置</Tag>}
              </Space>
            }
            extra={config?.has_api_key ? '留空保留已有 API Key。' : '当前未配置 API Key。'}
          >
            <Input.Password autoComplete="new-password" placeholder="留空则保留已有密钥" />
          </Form.Item>

          <Form.Item name="enabled" label="启用状态" valuePropName="checked">
            <Switch checkedChildren="已启用" unCheckedChildren="已停用" />
          </Form.Item>

          {config?.updated_at && <Paragraph type="secondary">最近更新：{new Date(config.updated_at).toLocaleString()}</Paragraph>}
          <Space>
            <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={saving}>保存配置</Button>
            <Text type="secondary">保存后将对新的研究任务生效</Text>
          </Space>
        </Form>
      </Card>
    </div>
  );
}
