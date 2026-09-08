import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Avatar,
  Button,
  Collapse,
  Drawer,
  Empty,
  Input,
  List,
  Space,
  Spin,
  Tag,
  Timeline,
  Typography,
  message,
} from 'antd';
import {
  BarsOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  MenuFoldOutlined,
  PlusOutlined,
  RobotOutlined,
  SendOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import ChatMessage from '../components/ChatMessage';
import type { AgentEvent, AgentMessage, AgentSession, AgentTurn, AgentTurnStatus } from '../types';
import {
  createAgentSession,
  getAgentSession,
  getAgentTurn,
  getApiErrorMessage,
  listAgentSessions,
  sendAgentMessage,
} from '../services/api';
import { createSSEParser } from '../utils/sse';
import styles from './AgentWorkspace.module.css';

const { Paragraph, Text, Title } = Typography;
const EXAMPLES = [
  { label: '开放问答', content: '请概述中药肝毒性研究中常见的风险评估思路。' },
  { label: '数据库查询', content: '查询数据库中与黄芪相关的化合物和证据，并注明来源。' },
  { label: '科研分析', content: '基于现有证据，分析黄芪与甘草配伍的潜在研究方向。' },
];
const EVENT_LABELS: Record<AgentEvent['type'], string> = {
  node_start: '节点开始',
  node_end: '节点完成',
  llm_start: '模型调用',
  llm_end: '模型完成',
  tool_call: '工具调用',
  tool_result: '工具结果',
  assistant_delta: '生成回答',
  error: '执行错误',
};
const SECRET_PATTERN = /(authorization|api[-_]?key|token|secret|password|cookie|credential)/i;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function redactSensitive(value: unknown, seen = new WeakSet<object>()): unknown {
  if (Array.isArray(value)) return value.map((item) => redactSensitive(item, seen));
  if (!isRecord(value)) return value;
  if (seen.has(value)) return '[Circular]';
  seen.add(value);
  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [
      key,
      SECRET_PATTERN.test(key) ? '[已隐藏]' : redactSensitive(item, seen),
    ]),
  );
}

function displayPayload(value: unknown): string {
  try {
    const normalized = typeof value === 'string' && /^[\s]*[\[{]/.test(value)
      ? JSON.parse(value) as unknown
      : value;
    return typeof normalized === 'string'
      ? normalized
      : JSON.stringify(redactSensitive(normalized), null, 2);
  } catch {
    return typeof value === 'string' ? value : '内容无法展示';
  }
}

function sessionId(session: AgentSession): string {
  return String(session.id ?? session.session_id ?? '');
}

function turnId(turn: AgentTurn): string {
  return turn.turn_id || turn.id || '';
}

function extractSessions(data: AgentSession[] | { sessions: AgentSession[] }): AgentSession[] {
  return Array.isArray(data) ? data : data.sessions;
}

function extractSession(data: AgentSession | { session: AgentSession }): AgentSession {
  return 'session' in data ? data.session : data;
}

function assistantMessage(turn: AgentTurn): AgentMessage | null {
  if (!turn.assistant_message) return null;
  if (typeof turn.assistant_message === 'string') {
    return { id: `assistant-${turnId(turn)}`, role: 'assistant', content: turn.assistant_message };
  }
  return turn.assistant_message;
}

function eventKey(event: AgentEvent, index: number): string {
  if (event.id || event.event_id) return event.id || event.event_id || '';
  if (event.sequence !== undefined) return `sequence-${event.sequence}`;
  return `${event.type}-${event.created_at || event.timestamp || ''}-${event.node || event.name || ''}-${event.tool_name || ''}-${event.tool_call_id || ''}-${index}`;
}

function mergeEvents(current: AgentEvent[], incoming: AgentEvent[]): AgentEvent[] {
  const merged = new Map<string, AgentEvent>();
  current.forEach((event, index) => merged.set(eventKey(event, index), event));
  incoming.forEach((event, index) => merged.set(eventKey(event, index), event));
  return Array.from(merged.values());
}

function EventTimeline({ events, status }: { events: AgentEvent[]; status: AgentTurnStatus | null }) {
  const visibleEvents = events.filter((event) => event.type !== 'assistant_delta');
  if (!visibleEvents.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={status ? '正在等待执行事件…' : '发送问题后，这里将实时展示 Agent 的执行过程'} />;
  }
  return (
    <Timeline
      className={styles.timeline}
      items={visibleEvents.map((event, index) => {
        const failed = event.type === 'error' || event.status === 'failed';
        const running = event.status === 'running' || event.type.endsWith('_start') || event.type === 'tool_call';
        const title = event.tool_name || event.node || event.name || EVENT_LABELS[event.type];
        return {
          color: failed ? 'red' : running ? 'gray' : 'green',
          dot: failed ? <CloseCircleOutlined /> : running ? <ClockCircleOutlined /> : event.type.startsWith('tool_') ? <ToolOutlined /> : <CheckCircleOutlined />,
          children: (
            <div className={styles.event}>
              <Space size={6} wrap>
                <Text strong>{title}</Text>
                <Tag bordered={false}>{EVENT_LABELS[event.type]}</Tag>
                {event.status && <Text type="secondary" className={styles.eventStatus}>{event.status}</Text>}
              </Space>
              {event.detail && <div className={styles.eventDetail}>{event.detail}</div>}
              {(event.input !== undefined || event.output !== undefined) && (
                <Collapse
                  ghost
                  size="small"
                  items={[
                    ...(event.input !== undefined ? [{ key: 'input', label: 'Input', children: <pre className={styles.payload}>{displayPayload(event.input)}</pre> }] : []),
                    ...(event.output !== undefined ? [{ key: 'output', label: 'Output', children: <pre className={styles.payload}>{displayPayload(event.output)}</pre> }] : []),
                  ]}
                />
              )}
            </div>
          ),
        };
      })}
    />
  );
}

export default function AgentWorkspace() {
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState('');
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [activeTurnId, setActiveTurnId] = useState('');
  const [turnStatus, setTurnStatus] = useState<AgentTurnStatus | null>(null);
  const [turnError, setTurnError] = useState('');
  const [input, setInput] = useState('');
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [loadingChat, setLoadingChat] = useState(false);
  const [sending, setSending] = useState(false);
  const [sessionDrawerOpen, setSessionDrawerOpen] = useState(false);
  const [traceDrawerOpen, setTraceDrawerOpen] = useState(false);
  const pollGeneration = useRef(0);
  const sendingRef = useRef(false);
  const messageEndRef = useRef<HTMLDivElement>(null);

  const activeSession = useMemo(
    () => sessions.find((session) => sessionId(session) === activeSessionId),
    [activeSessionId, sessions],
  );

  const loadSessions = useCallback(async (preferredId?: string) => {
    try {
      const response = await listAgentSessions();
      const next = extractSessions(response.data.data);
      setSessions(next);
      setActiveSessionId((current) => preferredId || current || (next[0] ? sessionId(next[0]) : ''));
    } catch (error: unknown) {
      message.error(getApiErrorMessage(error, '获取会话列表失败'));
    } finally {
      setLoadingSessions(false);
    }
  }, []);

  const loadSession = useCallback(async (id: string, resetTrace = true) => {
    setLoadingChat(true);
    try {
      const response = await getAgentSession(id);
      setMessages(response.data.data.messages || []);
      if (resetTrace) {
        setEvents([]);
        setTurnStatus(null);
        setTurnError('');
        setActiveTurnId('');
      }
    } catch (error: unknown) {
      message.error(getApiErrorMessage(error, '获取会话内容失败'));
    } finally {
      setLoadingChat(false);
    }
  }, []);

  useEffect(() => { void loadSessions(); }, [loadSessions]);
  useEffect(() => {
    pollGeneration.current += 1;
    if (activeSessionId) void loadSession(activeSessionId);
    else setMessages([]);
  }, [activeSessionId, loadSession]);
  useEffect(() => { messageEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, sending]);

  useEffect(() => {
    if (!activeSessionId || !activeTurnId) return undefined;
    const generation = ++pollGeneration.current;
    const controller = new AbortController();
    const temporaryMessageId = `stream-${activeTurnId}`;
    let timer: number | undefined;
    let stopped = false;
    let finished = false;

    const isCurrent = () => !stopped && generation === pollGeneration.current;
    const stopSending = () => {
      sendingRef.current = false;
      setSending(false);
      setActiveTurnId('');
    };
    const applyFinalTurn = (turn: AgentTurn) => {
      if (!isCurrent() || finished) return;
      finished = true;
      setTurnStatus(turn.status);
      setEvents((current) => mergeEvents(current, turn.events || []));
      if (turn.status === 'completed') {
        const reply = assistantMessage(turn);
        setMessages((current) => {
          const withoutTemporary = current.filter((item) => item.id !== temporaryMessageId);
          if (!reply) return withoutTemporary;
          const existingIndex = withoutTemporary.findIndex((item) => item.id === reply.id);
          if (existingIndex === -1) return [...withoutTemporary, reply];
          return withoutTemporary.map((item, index) => index === existingIndex ? reply : item);
        });
        stopSending();
        void Promise.all([loadSession(activeSessionId, false), loadSessions(activeSessionId)]);
        return;
      }
      if (turn.status === 'failed') {
        const errorText = turn.error || turn.error_message || 'Agent 执行失败';
        setMessages((current) => current.filter((item) => item.id !== temporaryMessageId));
        setTurnError(errorText);
        stopSending();
        message.error(errorText);
      }
    };
    const appendDelta = (delta: string) => {
      if (!delta || !isCurrent() || finished) return;
      setMessages((current) => {
        const index = current.findIndex((item) => item.id === temporaryMessageId);
        if (index === -1) return [...current, { id: temporaryMessageId, role: 'assistant', content: delta }];
        return current.map((item, itemIndex) => itemIndex === index ? { ...item, content: item.content + delta } : item);
      });
    };
    const processStreamEvent = (eventName: string, rawData: string) => {
      if (!rawData || eventName === 'heartbeat' || !isCurrent()) return;
      let payload: unknown;
      try {
        payload = JSON.parse(rawData) as unknown;
      } catch {
        return;
      }
      if (!isRecord(payload)) return;
      if (eventName === 'execution') {
        const nested = isRecord(payload.event) ? payload.event : isRecord(payload.data) ? payload.data : payload;
        if (typeof nested.type !== 'string') return;
        const executionEvent = nested as unknown as AgentEvent;
        setTurnStatus('running');
        setEvents((current) => mergeEvents(current, [executionEvent]));
        if (executionEvent.type === 'assistant_delta' && typeof executionEvent.delta === 'string') {
          appendDelta(executionEvent.delta);
        }
      } else if (eventName === 'turn') {
        const nested = isRecord(payload.turn) ? payload.turn : isRecord(payload.data) ? payload.data : payload;
        if (nested.status === 'completed' || nested.status === 'failed') {
          applyFinalTurn(nested as unknown as AgentTurn);
        } else if (nested.status === 'pending' || nested.status === 'running') {
          setTurnStatus(nested.status);
        }
      }
    };
    const poll = async () => {
      try {
        const response = await getAgentTurn(activeSessionId, activeTurnId);
        if (!isCurrent() || finished) return;
        const turn = response.data.data;
        setTurnStatus(turn.status);
        setEvents((current) => mergeEvents(current, turn.events || []));
        if (turn.status === 'completed' || turn.status === 'failed') {
          applyFinalTurn(turn);
          return;
        }
        timer = window.setTimeout(() => void poll(), 1000);
      } catch (error: unknown) {
        if (!isCurrent() || finished) return;
        const errorText = getApiErrorMessage(error, '获取执行状态失败');
        setTurnError(errorText);
        stopSending();
        message.error(errorText);
      }
    };
    const stream = async () => {
      try {
        const token = sessionStorage.getItem('token');
        const response = await fetch(`/api/agent/sessions/${encodeURIComponent(activeSessionId)}/turns/${encodeURIComponent(activeTurnId)}/stream`, {
          headers: {
            Accept: 'text/event-stream',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          signal: controller.signal,
        });
        if (!response.ok || !response.body) throw new Error(`SSE unavailable: ${response.status}`);
        const parser = createSSEParser(({ event, data }) => processStreamEvent(event, data));
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        while (isCurrent() && !finished) {
          const { done, value } = await reader.read();
          if (done) break;
          parser.feed(decoder.decode(value, { stream: true }));
        }
        parser.feed(decoder.decode());
        parser.end();
        if (!finished && isCurrent()) void poll();
      } catch (error: unknown) {
        if (!controller.signal.aborted && isCurrent() && !finished) void poll();
      }
    };
    void stream();
    return () => {
      stopped = true;
      controller.abort();
      if (timer) window.clearTimeout(timer);
    };
  }, [activeSessionId, activeTurnId, loadSession, loadSessions]);

  const createSession = async (title?: string): Promise<string | null> => {
    try {
      const response = await createAgentSession(title ? { title } : {});
      const session = extractSession(response.data.data);
      const id = sessionId(session);
      setSessions((current) => [session, ...current.filter((item) => sessionId(item) !== id)]);
      setActiveSessionId(id);
      setSessionDrawerOpen(false);
      return id;
    } catch (error: unknown) {
      message.error(getApiErrorMessage(error, '创建会话失败'));
      return null;
    }
  };

  const handleSend = async (preset?: string) => {
    const content = (preset ?? input).trim();
    if (!content || sendingRef.current) return;
    sendingRef.current = true;
    setSending(true);
    setInput('');
    setEvents([]);
    setTurnStatus('pending');
    setTurnError('');
    let targetSessionId: string | null = activeSessionId;
    if (!targetSessionId) {
      targetSessionId = await createSession(content.slice(0, 24));
      if (!targetSessionId) {
        sendingRef.current = false;
        setSending(false);
        return;
      }
    }
    const optimistic: AgentMessage = { id: `local-${Date.now()}`, role: 'user', content };
    setMessages((current) => [...current, optimistic]);
    try {
      const response = await sendAgentMessage(targetSessionId, { content });
      setTurnStatus(response.data.data.status);
      setActiveTurnId(response.data.data.turn_id);
    } catch (error: unknown) {
      const errorText = getApiErrorMessage(error, '发送消息失败');
      setMessages((current) => current.filter((item) => item.id !== optimistic.id));
      sendingRef.current = false;
      setSending(false);
      setTurnStatus('failed');
      setTurnError(errorText);
      message.error(errorText);
    }
  };

  const selectSession = (id: string) => {
    if (id === activeSessionId) {
      setSessionDrawerOpen(false);
      return;
    }
    pollGeneration.current += 1;
    sendingRef.current = false;
    setSending(false);
    setActiveTurnId('');
    setActiveSessionId(id);
    setSessionDrawerOpen(false);
  };

  const sessionPanel = (
    <div className={styles.sessionPanel}>
      <div className={styles.panelHeader}>
        <div><Text strong>会话</Text><div className={styles.panelHint}>你的研究记录</div></div>
        <Button type="text" icon={<PlusOutlined />} aria-label="新建会话" onClick={() => void createSession()} />
      </div>
      <List
        className={styles.sessionList}
        loading={loadingSessions}
        dataSource={sessions}
        locale={{ emptyText: '暂无会话' }}
        renderItem={(session) => {
          const id = sessionId(session);
          return (
            <List.Item className={`${styles.sessionItem} ${id === activeSessionId ? styles.activeSession : ''}`} onClick={() => selectSession(id)}>
              <div className={styles.sessionTitle}>{session.title || '新会话'}</div>
              {session.updated_at && <div className={styles.sessionTime}>{new Date(session.updated_at).toLocaleString()}</div>}
            </List.Item>
          );
        }}
      />
    </div>
  );

  const tracePanel = (
    <div className={styles.tracePanel}>
      <div className={styles.panelHeader}>
        <div><Text strong>执行轨迹</Text><div className={styles.panelHint}>实时、透明的 Agent 过程</div></div>
        {sending && <Spin size="small" />}
      </div>
      <div className={styles.traceBody}>
        {turnError && <Alert className={styles.traceError} type="error" showIcon message="执行失败" description={turnError} />}
        <EventTimeline events={events} status={turnStatus} />
      </div>
    </div>
  );

  return (
    <div className={styles.workspace}>
      <aside className={styles.sessionDesktop}>{sessionPanel}</aside>
      <section className={styles.chat}>
        <header className={styles.chatHeader}>
          <Button className={styles.mobileButton} type="text" icon={<MenuFoldOutlined />} onClick={() => setSessionDrawerOpen(true)} aria-label="打开会话列表" />
          <div className={styles.chatTitle}><Text strong>{activeSession?.title || '聊天 Agent 工作台'}</Text><span>中药毒理与循证研究助手</span></div>
          <Button className={styles.mobileButton} type="text" icon={<BarsOutlined />} onClick={() => setTraceDrawerOpen(true)} aria-label="打开执行轨迹" />
        </header>
        <div className={styles.messages}>
          {loadingChat ? <div className={styles.centerState}><Spin /></div> : messages.length ? messages.map((item, index) => <ChatMessage key={item.id || `${item.role}-${index}`} item={item} />) : (
            <div className={styles.welcome}>
              <RobotOutlined className={styles.welcomeIcon} />
              <Title level={3}>今天想研究什么？</Title>
              <Paragraph type="secondary">可以直接提问、查询数据库，或让 Agent 基于循证资料开展科研分析。</Paragraph>
              <Space wrap className={styles.examples}>{EXAMPLES.map((example) => <Button key={example.label} onClick={() => void handleSend(example.content)}>{example.label}</Button>)}</Space>
            </div>
          )}
          {sending && !messages.some((item) => item.id === `stream-${activeTurnId}`) && <div className={`${styles.messageRow} ${styles.assistantRow}`}><Avatar size={30} icon={<RobotOutlined />} className={styles.avatar} /><div className={`${styles.bubble} ${styles.assistantBubble}`}><Space><Spin size="small" /><Text type="secondary">正在生成…</Text></Space></div></div>}
          <div ref={messageEndRef} />
        </div>
        <div className={styles.composerWrap}>
          <div className={styles.composer}>
            <Input.TextArea value={input} onChange={(event) => setInput(event.target.value)} onPressEnter={(event) => { if (!event.shiftKey) { event.preventDefault(); void handleSend(); } }} autoSize={{ minRows: 1, maxRows: 6 }} placeholder="输入问题，Enter 发送，Shift + Enter 换行" disabled={sending} />
            <Button type="primary" shape="circle" icon={<SendOutlined />} disabled={!input.trim()} loading={sending} onClick={() => void handleSend()} aria-label="发送" />
          </div>
          <Text type="secondary" className={styles.disclaimer}>回答仅供研究参考，请结合原始证据审慎判断。</Text>
        </div>
      </section>
      <aside className={styles.traceDesktop}>{tracePanel}</aside>
      <Drawer title="会话" placement="left" width="min(88vw, 320px)" open={sessionDrawerOpen} onClose={() => setSessionDrawerOpen(false)} styles={{ body: { padding: 0 } }}>{sessionPanel}</Drawer>
      <Drawer title="执行轨迹" placement="right" width="min(92vw, 380px)" open={traceDrawerOpen} onClose={() => setTraceDrawerOpen(false)} styles={{ body: { padding: 0 } }}>{tracePanel}</Drawer>
    </div>
  );
}
