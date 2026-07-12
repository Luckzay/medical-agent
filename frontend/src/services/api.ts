import axios from 'axios';
import type {
  LoginRequest, LoginResponse, RegisterRequest, User,
  PaginatedResponse,
  HerbBasic, HerbDetail,
  DecoctionBasic, DecoctionDetail,
  HerbCoupletBasic, CoupletDetail,
  MolecularInfo,
  Expertise,
  Paper, PaperDetail,
} from '../types';

const api = axios.create({ baseURL: '/api' });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(err);
  },
);

// Auth
export const login = (data: LoginRequest) => api.post<LoginResponse>('/auth/login', data);
export const register = (data: RegisterRequest) => api.post<{ data: User }>('/auth/register', data);

// Users
export const listUsers = (page = 1, pageSize = 20) =>
  api.get<PaginatedResponse<User>>('/users', { params: { page, page_size: pageSize } });
export const createUser = (data: Partial<User> & { password: string }) => api.post<{ data: User }>('/users', data);
export const updateUser = (id: number, data: Partial<User>) => api.put(`/users/${id}`, data);
export const deleteUser = (id: number) => api.delete(`/users/${id}`);

// Herbs
export const listHerbs = (page = 1, pageSize = 20, keyword = '') =>
  api.get<PaginatedResponse<HerbBasic>>('/herbs', { params: { page, page_size: pageSize, keyword } });
export const getHerbDetail = (id: number) =>
  api.get<{ data: HerbDetail }>(`/herbs/${id}`);

// Decoctions
export const listDecoctions = (page = 1, pageSize = 20, keyword = '') =>
  api.get<PaginatedResponse<DecoctionBasic>>('/decoctions', { params: { page, page_size: pageSize, keyword } });
export const getDecoctionDetail = (id: number) =>
  api.get<{ data: DecoctionDetail }>(`/decoctions/${id}`);

// Couplets
export const listCouplets = (page = 1, pageSize = 20, keyword = '') =>
  api.get<PaginatedResponse<HerbCoupletBasic>>('/couplets', { params: { page, page_size: pageSize, keyword } });
export const getCoupletDetail = (id: number) =>
  api.get<{ data: CoupletDetail }>(`/couplets/${id}`);

// Compounds
export const listCompounds = (page = 1, pageSize = 20, keyword = '') =>
  api.get<PaginatedResponse<MolecularInfo>>('/compounds', { params: { page, page_size: pageSize, keyword } });
export const getCompoundDetail = (id: number) =>
  api.get<{ data: MolecularInfo }>(`/compounds/${id}`);

// Expertises
export const listExpertises = (page = 1, pageSize = 20, keyword = '') =>
  api.get<PaginatedResponse<Expertise>>('/expertises', { params: { page, page_size: pageSize, keyword } });
export const getExpertiseDetail = (id: number) =>
  api.get<{ data: Expertise }>(`/expertises/${id}`);

// Papers
export const listPapers = (page = 1, pageSize = 20, keyword = '') =>
  api.get<PaginatedResponse<Paper>>('/papers', { params: { page, page_size: pageSize, keyword } });
export const getPaperDetail = (id: number) =>
  api.get<{ data: PaperDetail }>(`/papers/${id}`);

export default api;
