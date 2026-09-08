import { RobotOutlined } from '@ant-design/icons';
import { Avatar, Spin } from 'antd';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { AgentMessage } from '../types';
import styles from '../pages/AgentWorkspace.module.css';

export default function ChatMessage({ item }: { item: AgentMessage }) {
  const assistant = item.role === 'assistant';
  const streaming = typeof item.id === 'string' && item.id.startsWith('stream-');

  return (
    <div className={`${styles.messageRow} ${assistant ? styles.assistantRow : styles.userRow}`}>
      {assistant && <Avatar size={30} icon={<RobotOutlined />} className={styles.avatar} />}
      <div className={`${styles.bubble} ${assistant ? styles.assistantBubble : styles.userBubble}`}>
        <div className={styles.messageMeta}>{assistant ? '研究 Agent' : '你'}</div>
        {assistant ? (
          <div className={styles.markdownContent}>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ children, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer">{children}</a>,
              }}
            >
              {item.content}
            </ReactMarkdown>
          </div>
        ) : <div className={styles.messageContent}>{item.content}</div>}
        {streaming && <div className={styles.generating}><Spin size="small" /> 正在生成…</div>}
      </div>
    </div>
  );
}
