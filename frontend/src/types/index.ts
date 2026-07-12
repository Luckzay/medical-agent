export interface User {
  id: number;
  username: string;
  full_name: string;
  phone: string;
  gender: string;
  email: string;
  role: 'admin' | 'user';
  created_at: string;
  updated_at: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RegisterRequest {
  username: string;
  password: string;
  full_name: string;
  phone: string;
  gender: string;
  email: string;
}

export interface LoginResponse {
  token: string;
  user: User;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface HerbBasic {
  id: number;
  herb_name: string;
  herb_name_pinyin: string;
  functionality: string;
  functionality_basis: string;
  link_to_functionality_basis: string;
  usage_and_dosage: string;
  basis_for_usage_and_dosage: string;
  link_to_usage_and_dosage: string;
  virulence: string;
  toxicity_mechanism: string;
  pathological_examination: string;
  crowd_taboo: string;
  symptom_contraindications: string;
  adr: string;
  typical_cases_of_adr: string;
  clinical_suggestion: string;
  clinical_suggestion_basis: string;
  link_to_clinical_suggestion: string;
  created_at: string;
  updated_at: string;
}

export interface HerbToxicCompound {
  id: number;
  herb_id: number;
  record_number: number;
  compound_type: string;
  compound_name: string;
  molecular_formula: string;
  cas: string;
}

export interface HerbDetail extends HerbBasic {
  toxic_compounds: HerbToxicCompound[];
  expertises: Expertise[];
}

export interface DecoctionBasic {
  id: number;
  decoction_name: string;
  decoction_name_pinyin: string;
  dosage_form: string;
  functionality: string;
  functionality_basis: string;
  link_to_functionality_basis: string;
  usage_and_dosage: string;
  basis_for_usage_and_dosage: string;
  link_to_usage_and_dosage: string;
  virulence: string;
  toxicity_mechanism: string;
  pathological_examination: string;
  crowd_taboo: string;
  symptom_contraindications: string;
  related_toxic_herbs: string;
  adr: string;
  typical_cases_of_adr: string;
  clinical_suggestion: string;
  clinical_suggestion_basis: string;
  link_to_clinical_suggestion: string;
  related_studies: string;
  link_to_related_studies: string;
  conclusion_of_related_studies: string;
  created_at: string;
  updated_at: string;
}

export interface DecoctionCompound {
  id: number;
  decoction_id: number;
  compound_type: string;
  compound_name: string;
  molecular_formula: string;
  cas: string;
}

export interface DecoctionToxicCompound {
  id: number;
  decoction_id: number;
  record_number: number;
  compound_type: string;
  compound_name: string;
  molecular_formula: string;
  cas: string;
}

export interface DecoctionMeta {
  id: number;
  decoction_id: number;
  review_number: number;
  systematic_review: string;
  link: string;
  sorting_number: number;
  index_value: string;
  study: string;
  quality_score: number;
  quality_evaluation_criteria: string;
  experimental_events: number;
  experimental_total: number;
  control_events: number;
  control_total: number;
  weight: string;
  or_or_rr: number;
  ci_95_lower: number;
  ci_95_upper: number;
  index_number: string;
  p_value: number;
  i2: string;
  model: string;
  tsa_analysis: string;
}

export interface DecoctionDetail extends DecoctionBasic {
  compounds: DecoctionCompound[];
  toxic_compounds: DecoctionToxicCompound[];
  meta: DecoctionMeta[];
}

export interface HerbCoupletBasic {
  id: number;
  herb_couplet_name: string;
  herb_couplet_name_pinyin: string;
  functionality: string;
  functionality_basis: string;
  link_to_functionality_basis: string;
  virulence: string;
  toxicity_mechanism: string;
  pathological_examination: string;
  crowd_taboo: string;
  symptom_contraindications: string;
  related_toxic_herbs: string;
  adr: string;
  typical_cases_of_adr: string;
  clinical_suggestion: string;
  clinical_suggestion_basis: string;
  link_to_clinical_suggestion: string;
  created_at: string;
  updated_at: string;
}

export interface CoupletToxicCompound {
  id: number;
  couplet_id: number;
  record_number: number;
  compound_type: string;
  compound_name: string;
  molecular_formula: string;
  cas: string;
}

export interface CoupletDetail extends HerbCoupletBasic {
  toxic_compounds: CoupletToxicCompound[];
}

export interface MolecularInfo {
  record_number: number;
  record_title: string;
  record_description: string;
  fda_pharmacology_summary: string;
  livertox_summary: string;
  inchi: string;
  inchi_key: string;
  smiles: string;
  molecular_formula: string;
  molecular_weight: number;
  xlogp3: number;
  hydrogen_bond_donor_count: number;
  hydrogen_bond_acceptor_count: number;
  rotatable_bond_count: number;
  heavy_atom_count: number;
  created_at: string;
}

export interface Expertise {
  id: number;
  herb_id: number;
  related_article: string;
  link_article: string;
  author: string;
  abstract: string;
  herb_or_decoction: string;
  application_situation: string;
  dosage_course_usage: string;
  couplet: string;
  clinical_case: string;
  related_literature: string;
}

export interface Paper {
  id: number;
  title: string;
  authors: string;
  journal: string;
  year: number;
  abstract: string;
  doi: string;
  source_db: string;
  created_at: string;
}

export interface PaperTag {
  paper_id: number;
  tag: string;
}

export interface PaperDetail extends Paper {
  tags: PaperTag[];
}
