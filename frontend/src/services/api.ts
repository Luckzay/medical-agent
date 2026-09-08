import axios from 'axios';
import type {
  LoginRequest, LoginResponse, RegisterRequest, User, UserStatus,
  PaginatedResponse, DynamicRecord, CaseClauseDetail,
  HerbBasic, HerbDetail,
  DecoctionBasic, DecoctionDetail,
  HerbCoupletBasic, CoupletDetail,
  MolecularInfo,
  Expertise,
  Paper, PaperDetail,
  AgentRun, CreateAgentRunRequest,
  AgentSession, AgentSessionDetail, AgentTurn,
  CreateAgentSessionRequest, SendAgentMessageRequest, SendAgentMessageResponse,
  LLMConfig, UpdateLLMConfigRequest,
} from '../types';

const api = axios.create({ baseURL: '/api' });

function stripSystemFields<T extends object>(data: T): Partial<T> {
  const cleaned = { ...data } as Record<string, unknown>;
  delete cleaned.created_at;
  delete cleaned.updated_at;
  return cleaned as Partial<T>;
}

function stripBlankPassword<T extends object>(data: T): Partial<T> {
  const cleaned = stripSystemFields(data) as Record<string, unknown>;
  if (cleaned.password === '') {delete cleaned.password;}
  return cleaned as Partial<T>;
}

api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('token');
  if (token) {config.headers.Authorization = `Bearer ${token}`;}
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (error: unknown) => {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      sessionStorage.removeItem('token');
      sessionStorage.removeItem('user');
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  },
);

interface APIErrorBody {
  error?: string;
  message?: string;
}

export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (!axios.isAxiosError<APIErrorBody>(error)) {return fallback;}
  return error.response?.data?.error || error.response?.data?.message || error.message || fallback;
}

// Auth
export const login = (data: LoginRequest) => api.post<LoginResponse>('/auth/login', data);
export const register = (data: RegisterRequest) => api.post<{ data: User }>('/auth/register', data);

// Users
export const listUsers = (page = 1, pageSize = 20) =>
  api.get<PaginatedResponse<User>>('/users', { params: { page, page_size: pageSize } });
export const createUser = (data: Partial<User> & { password: string }) => api.post<{ data: User }>('/users', stripSystemFields(data));
export const updateUser = (id: number, data: Partial<User>) => api.put(`/users/${id}`, stripBlankPassword(data));
export const deleteUser = (id: number) => api.delete(`/users/${id}`);
export const updateUserStatus = (id: number, status: UserStatus) =>
  api.patch<{ data: User }>(`/users/${id}/status`, { status });

// Herbs
export const listHerbs = (page = 1, pageSize = 20, keyword = '') =>
  api.get<PaginatedResponse<HerbBasic>>('/herbs', { params: { page, page_size: pageSize, keyword } });
export const getHerbDetail = (id: number) =>
  api.get<{ data: HerbDetail }>(`/herbs/${id}`);
export const createHerb = (data: Partial<HerbBasic>) => api.post<{ data: HerbBasic }>('/herbs', stripSystemFields(data));
export const updateHerb = (id: number, data: Partial<HerbBasic>) => api.put(`/herbs/${id}`, stripSystemFields(data));
export const deleteHerb = (id: number) => api.delete(`/herbs/${id}`);

// Decoctions
export const listDecoctions = (page = 1, pageSize = 20, keyword = '') =>
  api.get<PaginatedResponse<DecoctionBasic>>('/decoctions', { params: { page, page_size: pageSize, keyword } });
export const getDecoctionDetail = (id: number) =>
  api.get<{ data: DecoctionDetail }>(`/decoctions/${id}`);
export const createDecoction = (data: Partial<DecoctionBasic>) => api.post<{ data: DecoctionBasic }>('/decoctions', stripSystemFields(data));
export const updateDecoction = (id: number, data: Partial<DecoctionBasic>) => api.put(`/decoctions/${id}`, stripSystemFields(data));
export const deleteDecoction = (id: number) => api.delete(`/decoctions/${id}`);

// Couplets
export const listCouplets = (page = 1, pageSize = 20, keyword = '') =>
  api.get<PaginatedResponse<HerbCoupletBasic>>('/couplets', { params: { page, page_size: pageSize, keyword } });
export const getCoupletDetail = (id: number) =>
  api.get<{ data: CoupletDetail }>(`/couplets/${id}`);
export const createCouplet = (data: Partial<HerbCoupletBasic>) => api.post<{ data: HerbCoupletBasic }>('/couplets', stripSystemFields(data));
export const updateCouplet = (id: number, data: Partial<HerbCoupletBasic>) => api.put(`/couplets/${id}`, stripSystemFields(data));
export const deleteCouplet = (id: number) => api.delete(`/couplets/${id}`);

// Compounds
export const listCompounds = (page = 1, pageSize = 20, keyword = '') =>
  api.get<PaginatedResponse<MolecularInfo>>('/compounds', { params: { page, page_size: pageSize, keyword } });
export const getCompoundDetail = (id: number) =>
  api.get<{ data: MolecularInfo }>(`/compounds/${id}`);
export const createCompound = (data: Partial<MolecularInfo>) => api.post<{ data: MolecularInfo }>('/compounds', stripSystemFields(data));
export const updateCompound = (id: number, data: Partial<MolecularInfo>) => api.put(`/compounds/${id}`, stripSystemFields(data));
export const deleteCompound = (id: number) => api.delete(`/compounds/${id}`);

// Cases and clauses with unknown main-table schemas
export const listCases = (page = 1, pageSize = 20) =>
  api.get<PaginatedResponse<DynamicRecord>>('/cases', { params: { page, page_size: pageSize } });
export const getCaseDetail = (id: string | number) =>
  api.get<{ data: CaseClauseDetail }>(`/cases/${encodeURIComponent(id)}`);
export const listClauses = (page = 1, pageSize = 20) =>
  api.get<PaginatedResponse<DynamicRecord>>('/clauses', { params: { page, page_size: pageSize } });
export const getClauseDetail = (id: string | number) =>
  api.get<{ data: CaseClauseDetail }>(`/clauses/${encodeURIComponent(id)}`);

// Expertises
export const listExpertises = (page = 1, pageSize = 20, keyword = '') =>
  api.get<PaginatedResponse<Expertise>>('/expertises', { params: { page, page_size: pageSize, keyword } });
export const getExpertiseDetail = (id: number) =>
  api.get<{ data: Expertise }>(`/expertises/${id}`);
export const createExpertise = (data: Partial<Expertise>) => api.post<{ data: Expertise }>('/expertises', stripSystemFields(data));
export const updateExpertise = (id: number, data: Partial<Expertise>) => api.put(`/expertises/${id}`, stripSystemFields(data));
export const deleteExpertise = (id: number) => api.delete(`/expertises/${id}`);

// Papers
export const listPapers = (page = 1, pageSize = 20, keyword = '') =>
  api.get<PaginatedResponse<Paper>>('/papers', { params: { page, page_size: pageSize, keyword } });
export const getPaperDetail = (id: number) =>
  api.get<{ data: PaperDetail }>(`/papers/${id}`);
export const createPaper = (data: Partial<Paper>) => api.post<{ data: Paper }>('/papers', stripSystemFields(data));
export const updatePaper = (id: number, data: Partial<Paper>) => api.put(`/papers/${id}`, stripSystemFields(data));
export const deletePaper = (id: number) => api.delete(`/papers/${id}`);

export default api;


// Agent runs
export const createAgentRun = (data: CreateAgentRunRequest) =>
  api.post<{ data: AgentRun }>('/agent/runs', data);
export const getAgentRun = (runId: string) =>
  api.get<{ data: AgentRun }>(`/agent/runs/${encodeURIComponent(runId)}`);
export const resumeAgentRun = (runId: string) =>
  api.post<{ data: AgentRun }>(`/agent/runs/${encodeURIComponent(runId)}/resume`);

// Agent chat workspace
export const createAgentSession = (data: CreateAgentSessionRequest) =>
  api.post<{ data: AgentSession | { session: AgentSession } }>('/agent/sessions', data);
export const listAgentSessions = () =>
  api.get<{ data: AgentSession[] | { sessions: AgentSession[] } }>('/agent/sessions');
export const getAgentSession = (sessionId: string) =>
  api.get<{ data: AgentSessionDetail }>(`/agent/sessions/${encodeURIComponent(sessionId)}`);
export const sendAgentMessage = (sessionId: string, data: SendAgentMessageRequest) =>
  api.post<{ data: SendAgentMessageResponse }>(`/agent/sessions/${encodeURIComponent(sessionId)}/messages`, data);
export const getAgentTurn = (sessionId: string, turnId: string) =>
  api.get<{ data: AgentTurn }>(`/agent/sessions/${encodeURIComponent(sessionId)}/turns/${encodeURIComponent(turnId)}`);

// LLM configuration (admin only)
export const getLLMConfig = () => api.get<LLMConfig>('/admin/llm-config');
export const updateLLMConfig = (data: UpdateLLMConfigRequest) =>
  api.put<{ message: string }>('/admin/llm-config', data);
