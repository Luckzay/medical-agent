import { useEffect, useMemo, useState } from 'react';
import { Table, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useNavigate, useSearchParams } from 'react-router-dom';
import type { DynamicRecord, PaginatedResponse } from '../types';
import { listCases, listClauses } from '../services/api';
import { useAuth } from '../hooks/useAuth';
import GuestListNotice from '../components/GuestListNotice';
import { getRecordId, renderDynamicValue } from '../utils/dynamicRecord';
import styles from './ListPage.module.css';

const { Title } = Typography;
const pageSize = 20;

interface CaseClauseListProps {
  kind: 'cases' | 'clauses';
}

const pageConfig = {
  cases: {
    title: '治疗无效/加重的医案',
    emptyText: '暂无医案数据',
    request: listCases,
  },
  clauses: {
    title: '治疗无效/加重的条文及论述',
    emptyText: '暂无条文及论述数据',
    request: listClauses,
  },
};

export default function CaseClauseList({ kind }: CaseClauseListProps) {
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedPage = Number(searchParams.get('page')) || 1;
  const [page, setPage] = useState(isAuthenticated ? requestedPage : 1);
  const [data, setData] = useState<DynamicRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const config = pageConfig[kind];

  useEffect(() => {
    if (!isAuthenticated && page > 1) {
      setPage(1);
      setSearchParams({ page: '1' }, { replace: true });
    }
  }, [isAuthenticated, page, setSearchParams]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    config.request(page, pageSize)
      .then((response: { data: PaginatedResponse<DynamicRecord> }) => {
        if (!active) {
          return;
        }
        setData(response.data.data);
        setTotal(response.data.total);
      })
      .catch(() => {
        if (active) {
          message.error(`加载${config.title}失败`);
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [config, page]);

  const columns = useMemo<ColumnsType<DynamicRecord>>(() => {
    const firstValue = (record: DynamicRecord, fields: string[]) => {
      const field = fields.find((name) => record[name] !== undefined && record[name] !== null && record[name] !== '');
      return field ? record[field] : undefined;
    };
    const excerpt = (value: unknown, length: number) => {
      const text = value === undefined || value === null || value === '' ? '-' : String(value);
      return text === '-' ? text : `${Array.from(text).slice(0, length).join('')}...`;
    };
    const linkedSource = (record: DynamicRecord) => {
      const content = renderDynamicValue(firstValue(record, ['source', 'filename']));
      const id = getRecordId(record);
      return id === undefined
        ? content
        : <a onClick={() => navigate(`/${kind}/${encodeURIComponent(id)}`)}>{content}</a>;
    };

    if (kind === 'cases') {
      return [
        { title: '来源', key: 'source', width: 180, ellipsis: true, render: (_: unknown, record) => linkedSource(record) },
        { title: '主诉', key: 'main_complaint', ellipsis: true, render: (_: unknown, record) => renderDynamicValue(record.main_complaint) },
        { title: '性别', key: 'gender', width: 100, render: (_: unknown, record) => renderDynamicValue(firstValue(record, ['patient_gender', 'gender'])) },
        { title: '原文', key: 'original_text', width: 180, render: (_: unknown, record) => excerpt(record.original_text, 10) },
      ];
    }

    return [
      { title: '来源', key: 'source', width: 180, ellipsis: true, render: (_: unknown, record) => linkedSource(record) },
      { title: '原文', key: 'original_text', render: (_: unknown, record) => excerpt(firstValue(record, ['original_text', 'clause', 'target_content']), 15) },
    ];
  }, [kind, navigate]);

  const visibleTotal = isAuthenticated ? total : Math.min(total, pageSize);

  return (
    <div>
      <Title level={3} className={styles.pageTitle}>{config.title}</Title>
      <Table
        columns={columns}
        dataSource={data}
        rowKey={(record, index) => String(getRecordId(record) ?? index)}
        loading={loading}
        locale={{ emptyText: config.emptyText }}
        scroll={{ x: 'max-content' }}
        pagination={{
          current: page,
          total: visibleTotal,
          pageSize,
          hideOnSinglePage: true,
          onChange: (nextPage) => {
            setPage(nextPage);
            setSearchParams({ page: String(nextPage) });
          },
          showTotal: (count) => `共 ${count} 条`,
        }}
        onRow={(record) => {
          const id = getRecordId(record);
          return id === undefined ? {} : {
            onClick: () => navigate(`/${kind}/${encodeURIComponent(id)}`),
            style: { cursor: 'pointer' },
          };
        }}
      />
      <GuestListNotice total={total} pageSize={pageSize} />
    </div>
  );
}
