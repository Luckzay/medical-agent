import { Alert } from 'antd';
import { Link } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

interface GuestListNoticeProps {
  total: number;
  pageSize: number;
}

export default function GuestListNotice({ pageSize }: GuestListNoticeProps) {
  const { isAuthenticated } = useAuth();

  if (isAuthenticated) {
    return null;
  }

  return (
    <Alert
      type="info"
      showIcon
      message={<>游客仅可查看每类数据的前 {pageSize} 条，<Link to="/login">登录后查看更多</Link></>}
      style={{ marginTop: 16 }}
    />
  );
}
