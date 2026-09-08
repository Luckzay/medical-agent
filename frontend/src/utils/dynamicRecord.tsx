import type { ReactNode } from 'react';

const hiddenFields = new Set([
  'id', 'case_id', 'clause_id', 'herb_id', 'decoction_id', 'user_id',
  'created_at', 'updated_at', 'deleted_at', 'created_by', 'updated_by',
]);

const fieldLabels: Record<string, string> = {
  record_number: '编号',
  title: '标题',
  name: '名称',
  case_title: '医案标题',
  clause_title: '条文标题',
  patient: '患者信息',
  patient_info: '患者信息',
  gender: '性别',
  age: '年龄',
  source: '来源',
  author: '作者',
  dynasty: '朝代',
  book: '书名',
  chapter: '章节',
  original_text: '原文',
  clause: '条文',
  content: '内容',
  discussion: '论述',
  analysis: '分析',
  diagnosis: '诊断',
  syndrome: '证候',
  symptoms: '症状',
  treatment: '治法',
  prescription: '处方',
  dosage: '剂量',
  course: '疗程',
  outcome: '治疗结果',
  result: '结果',
  reason: '原因',
  failure_reason: '无效原因',
  aggravation: '加重情况',
  notes: '备注',
  reference: '参考资料',
  link: '链接',
  filename: '来源文件',
  result_type: '结果类型',
  target_content: '目标内容',
  symptom_description: '症状描述',
  intervention_method: '干预方法',
  explanation_of_ineffectiveness: '无效或加重原因',
  combined_explanation: '综合论述',
  patient_age: '患者年龄',
  patient_gender: '患者性别',
  main_complaint: '主诉',
  symptoms_and_history: '症状与病史',
  past_history: '既往史',
  treatment_principle: '治疗原则',
  specific_treatment: '具体治疗',
  response_to_treatment: '治疗反应',
  adjustment_for_ineffectiveness: '治疗无效后的调整',
};

const preferredFields = [
  'record_number', 'case_title', 'clause_title', 'title', 'name', 'target_content',
  'main_complaint', 'patient_info', 'patient_age', 'patient_gender', 'symptom_description',
  'symptoms_and_history', 'intervention_method', 'treatment_principle', 'specific_treatment',
  'response_to_treatment', 'explanation_of_ineffectiveness', 'combined_explanation',
  'diagnosis', 'syndrome', 'symptoms', 'original_text', 'clause', 'content',
  'outcome', 'result', 'failure_reason', 'result_type', 'source', 'author',
];

export function isBusinessField(key: string): boolean {
  return !hiddenFields.has(key) && !key.endsWith('_id') && !key.startsWith('_');
}

export function hasDisplayValue(value: unknown): boolean {
  return value !== null && value !== undefined && value !== '' &&
    (!Array.isArray(value) || value.length > 0) &&
    (typeof value !== 'object' || Array.isArray(value) || Object.keys(value as object).length > 0);
}

export function getFieldLabel(key: string): string {
  if (fieldLabels[key]) {
    return fieldLabels[key];
  }
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function getRecordId(record: Record<string, unknown>): string | number | undefined {
  const candidates = ['id', 'case_id', 'clause_id', 'record_id', 'record_number'];
  const value = candidates.map((key) => record[key]).find((item) =>
    typeof item === 'string' || typeof item === 'number',
  );
  return value as string | number | undefined;
}

export function getRecordTitle(record: Record<string, unknown>, fallback: string): string {
  const candidates = [
    'case_title', 'clause_title', 'title', 'name', 'record_title', 'target_content',
    'main_complaint', 'diagnosis', 'original_text', 'symptom_description',
  ];
  const value = candidates.map((key) => record[key]).find((item) => typeof item === 'string' && item.trim());
  return typeof value === 'string' ? value : fallback;
}

export function pickListFields(records: Array<Record<string, unknown>>, limit = 5): string[] {
  const available = Array.from(new Set(records.flatMap((record) => Object.keys(record))))
    .filter((key) => isBusinessField(key))
    .filter((key) => records.some((record) => hasDisplayValue(record[key])))
    .filter((key) => records.some((record) => {
      const value = record[key];
      return typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean';
    }));

  return available
    .sort((a, b) => {
      const aIndex = preferredFields.indexOf(a);
      const bIndex = preferredFields.indexOf(b);
      return (aIndex < 0 ? preferredFields.length : aIndex) -
        (bIndex < 0 ? preferredFields.length : bIndex);
    })
    .slice(0, limit);
}

export function renderDynamicValue(value: unknown): ReactNode {
  if (typeof value === 'boolean') {
    return value ? '是' : '否';
  }
  if (typeof value === 'string' && /^https?:\/\//i.test(value)) {
    return <a href={value} target="_blank" rel="noreferrer">查看链接</a>;
  }
  if (Array.isArray(value)) {
    return value.map((item) =>
      typeof item === 'object' ? JSON.stringify(item) : String(item),
    ).join('、');
  }
  if (typeof value === 'object' && value !== null) {
    return (
      <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{JSON.stringify(value, null, 2)}</pre>
    );
  }
  return String(value);
}
