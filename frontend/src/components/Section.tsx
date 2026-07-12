import { LinkOutlined } from '@ant-design/icons';
import styles from './Section.module.css';

interface SectionProps {
  title: string;
  text?: string;
  basis?: string;
  link?: string;
}

export default function Section({ title, text, basis, link }: SectionProps) {
  if (!text) return null;
  return (
    <div className={styles.section}>
      <div className={styles.sectionTitle}>{title}</div>
      <div className={styles.sectionBody}>{text}</div>
      {basis && (
        <div className={styles.sectionBasis}>
          依据: {basis}
          {link && (
            <a
              href={link}
              target="_blank"
              rel="noopener noreferrer"
              className={styles.sectionLink}
            >
              <LinkOutlined /> 查看原文
            </a>
          )}
        </div>
      )}
    </div>
  );
}
