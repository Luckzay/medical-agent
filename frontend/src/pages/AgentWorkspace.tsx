import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Collapse,
  Descriptions,
  Empty,
  Form,
  Input,
  List,
  Space,
  Spin,
  Table,
  Tag,
  Timeline,
  Typography,
  message,
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExperimentOutlined,
  ReloadOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import type { AgentRun, AgentRunStatus, Evidence } from '../types';
import { createAgentRun, getAgentRun, getApiErrorMessage, resumeAgentRun } from '../services/api';
import styles from './AgentWorkspace.module.css';

const { Title, Paragraph, Text } = Typography;
const ACTIVE_STATUSES: AgentRunStatus[] = ['pending', 'running', 'dispatch_unknown'];

const STATUS_META: Record<AgentRunStatus, { label: string; color: string }> = {
  pending: { label: '等待中', color: 'default' },
  running: { label: '运行中', color: 'processing' },
  completed: { label: '已完成', color: 'success' },
  failed: { label: '失败', color: 'error' },
  cancelled: { label: '已取消', color: 'default' },
  dispatch_unknown: { label: '调度确认中', color: 'warning' },
};

function JsonPanel({ value }: { value: unknown }) {
  return (
    <Collapse
      ghost
      items={[{
        key: 'json',
        label: '查看原始 JSON',
        children: <pre className={styles.json}>{JSON.stringify(value, null, 2)}</pre>,
      }]}
    />
  );
}

function EvidenceList({ evidence }: { evidence: Evidence[] }) {
  if (!evidence.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无证据" />;
  return (
    <List
      dataSource={evidence}
      renderItem={(item) => (
        <List.Item>
          <List.Item.Meta
            title={item.link ? <a href={item.link} target="_blank" rel="noreferrer">{item.title || item.reference}</a> : item.title || item.reference}
            description={
              <Space size={[8, 4]} wrap>
                <Tag>{item.source_type}</Tag>
                <Text type="secondary">{item.source}</Text>
                {item.year && <Text type="secondary">{item.year}</Text>}
                {typeof item.score === 'number' && <Text type="secondary">相关度 {item.score.toFixed(2)}</Text>}
              </Space>
            }
          />
        </List.Item>
      )}
    />
  );
}

export default function AgentWorkspace() {
  const [form] = Form.useForm<{ herbs: string; researchGoal: string }>();
  const [run, setRun] = useState<AgentRun | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [resuming, setResuming] = useState(false);

  const herbs = useMemo(() => run?.herbs ?? [], [run?.herbs]);
  const isActive = run ? ACTIVE_STATUSES.includes(run.status) : false;

  const refreshRun = useCallback(async (runId: string, showError = true) => {
    try {
      const response = await getAgentRun(runId);
      setRun(response.data.data);
    } catch (error: unknown) {
      if (showError) message.error(getApiErrorMessage(error, '获取任务状态失败'));
    }
  }, []);

  useEffect(() => {
    if (!run?.run_id || !isActive) return undefined;
    const timer = window.setInterval(() => void refreshRun(run.run_id, false), 2500);
    return () => window.clearInterval(timer);
  }, [isActive, refreshRun, run?.run_id]);

  const handleSubmit = async (values: { herbs: string; researchGoal: string }) => {
    const parsedHerbs = Array.from(new Set(values.herbs.split(/[，,\s]+/).map((item) => item.trim()).filter(Boolean)));
    if (!parsedHerbs.length) {
      message.warning('请至少输入一味药名');
      return;
    }
    setSubmitting(true);
    try {
      const response = await createAgentRun({ herbs: parsedHerbs, research_goal: values.researchGoal.trim() });
      setRun(response.data.data);
      message.success('研究任务已创建');
    } catch (error: unknown) {
      message.error(getApiErrorMessage(error, '创建研究任务失败'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleResume = async () => {
    if (!run) return;
    setResuming(true);
    try {
      const response = await resumeAgentRun(run.run_id);
      setRun(response.data.data);
      message.success('任务已恢复');
    } catch (error: unknown) {
      message.error(getApiErrorMessage(error, '恢复任务失败'));
    } finally {
      setResuming(false);
    }
  };

  const result = run?.analysis_result;
  const workflow = run?.workflow ?? result?.workflow;
  const statusMeta = run ? STATUS_META[run.status] : null;

  return (
    <div className={styles.page}>
      <div className={styles.heading}>
        <div>
          <Title level={2}>智能研究工作台</Title>
          <Paragraph type="secondary">聚合中药化合物、循证依据与实验建议，任务可在后台持续运行。</Paragraph>
        </div>
        <ExperimentOutlined className={styles.headingIcon} />
      </div>

      <Card className={styles.card} title="创建研究任务">
        <Form form={form} layout="vertical" onFinish={handleSubmit} requiredMark="optional">
          <Form.Item
            name="herbs"
            label="中药名称"
            rules={[{ required: true, message: '请输入中药名称' }]}
            extra="支持中文逗号、空格或换行分隔，将自动去重。"
          >
            <Input.TextArea rows={3} placeholder={'例如：黄芪，当归\n甘草'} />
          </Form.Item>
          <Form.Item
            name="researchGoal"
            label="研究目标"
            rules={[{ required: true, whitespace: true, message: '请填写研究目标' }]}
          >
            <Input.TextArea rows={3} placeholder="描述希望重点分析的毒理机制、候选化合物或实验方向" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={submitting} icon={<ExperimentOutlined />}>
            启动研究
          </Button>
        </Form>
      </Card>

      {run && statusMeta && (
        <>
          <Card
            className={styles.card}
            title={<Space><span>任务状态</span><Tag color={statusMeta.color}>{statusMeta.label}</Tag>{isActive && <Spin size="small" />}</Space>}
            extra={
              <Space>
                <Button size="small" icon={<ReloadOutlined />} onClick={() => void refreshRun(run.run_id)}>刷新</Button>
                {run.status === 'failed' && <Button size="small" type="primary" loading={resuming} onClick={handleResume}>恢复任务</Button>}
              </Space>
            }
          >
            <Descriptions size="small" column={{ xs: 1, sm: 2 }}>
              <Descriptions.Item label="Run ID"><Text copyable>{run.run_id}</Text></Descriptions.Item>
              <Descriptions.Item label="Trace ID"><Text copyable>{run.trace_id}</Text></Descriptions.Item>
              <Descriptions.Item label="药物">{herbs.join('、')}</Descriptions.Item>
              <Descriptions.Item label="研究目标">{run.research_goal || '—'}</Descriptions.Item>
              <Descriptions.Item label="更新时间">{new Date(run.updated_at).toLocaleString()}</Descriptions.Item>
            </Descriptions>
            {run.error_message && <Alert className={styles.alert} type="error" showIcon message="任务执行失败" description={run.error_message} />}
          </Card>

          <Card className={styles.card} title="工作流">
            {workflow?.steps?.length ? (
              <Timeline
                items={workflow.steps.map((step) => ({
                  color: step.status === 'completed' ? 'green' : step.status === 'failed' ? 'red' : 'blue',
                  dot: step.status === 'running' ? <SyncOutlined spin /> : step.status === 'failed' ? <CloseCircleOutlined /> : <CheckCircleOutlined />,
                  children: (
                    <div>
                      <Space wrap><Text strong>{step.node}</Text><Tag>{step.status}</Tag></Space>
                      <div className={styles.stepDetail}>{step.detail || '—'}</div>
                    </div>
                  ),
                }))}
              />
            ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={isActive ? '工作流正在初始化' : '暂无工作流信息'} />}
          </Card>
        </>
      )}

      {run?.status === 'completed' && result && (
        <div className={styles.results}>
          <Card className={styles.card} title="智能摘要" extra={<Tag>{result.llm_status || 'disabled'}</Tag>}>
            <Paragraph className={styles.summary}>{result.llm_summary || '本次任务未生成 LLM 摘要。'}</Paragraph>
            {result.summary && (
              <Space size={[16, 8]} wrap>
                <Text>药物 {result.summary.herb_count}</Text>
                <Text>化合物 {result.summary.compound_count}</Text>
                <Text>候选物 {result.summary.candidate_count}</Text>
              </Space>
            )}
          </Card>

          <Card className={styles.card} title={`候选化合物（${result.compounds?.length ?? 0}）`}>
            <Table
              size="small"
              pagination={{ pageSize: 8, hideOnSinglePage: true }}
              rowKey="compound_id"
              dataSource={result.compounds ?? []}
              scroll={{ x: 680 }}
              columns={[
                { title: '名称', dataIndex: 'name', key: 'name', width: 150 },
                { title: '来源中药', dataIndex: 'herb', key: 'herb', width: 120 },
                { title: 'PubChem CID', dataIndex: 'pubchem_cid', key: 'pubchem_cid', width: 130, render: (value: number | null) => value ?? '—' },
                { title: '评分', key: 'score', width: 100, render: (_, item) => item.candidate_score.total_score },
                { title: '候选', key: 'candidate', width: 90, render: (_, item) => <Tag color={item.candidate_score.is_candidate ? 'success' : 'default'}>{item.candidate_score.is_candidate ? '是' : '否'}</Tag> },
                { title: 'SMILES', dataIndex: 'smiles', key: 'smiles', ellipsis: true },
              ]}
              locale={{ emptyText: '暂无化合物' }}
            />
          </Card>

          <Card className={styles.card} title={`循证依据（${result.evidence?.length ?? 0}）`}>
            <EvidenceList evidence={result.evidence ?? []} />
          </Card>

          {result.proposal && (
            <Card className={styles.card} title="实验方案">
              <Title level={4}>{result.proposal.title}</Title>
              <Descriptions size="small" column={1} bordered>
                <Descriptions.Item label="入选化合物">{result.proposal.selected_compounds?.map((item) => item.name).join('、') || '—'}</Descriptions.Item>
                <Descriptions.Item label="研究假设">
                  <List size="small" dataSource={result.proposal.hypotheses ?? []} renderItem={(item) => <List.Item>{item.statement}</List.Item>} />
                </Descriptions.Item>
                <Descriptions.Item label="安全声明">{result.proposal.safety_disclaimer || '—'}</Descriptions.Item>
                <Descriptions.Item label="研究声明">{result.proposal.research_disclaimer || '—'}</Descriptions.Item>
              </Descriptions>
            </Card>
          )}

          {result.proposal_review && (
            <Card className={styles.card} title="方案审核" extra={<Space><Tag>{result.proposal_review.status}</Tag><Text strong>{result.proposal_review.score} 分</Text></Space>}>
              <List
                dataSource={result.proposal_review.issues ?? []}
                locale={{ emptyText: '未发现审核问题' }}
                renderItem={(issue) => (
                  <List.Item>
                    <List.Item.Meta title={<Space><Tag color={issue.severity === 'critical' || issue.severity === 'error' ? 'error' : 'warning'}>{issue.severity}</Tag>{issue.message}</Space>} description={issue.field_path} />
                  </List.Item>
                )}
              />
            </Card>
          )}

          <Card className={styles.card}><JsonPanel value={result} /></Card>
        </div>
      )}
    </div>
  );
}
