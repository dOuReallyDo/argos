const BASE = '/api';

async function request<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...opts?.headers,
    },
    ...opts,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

export interface Source {
  id: string;
  source_type: string;
  source_value: string;
  created_at: string;
}

export interface DocRecord {
  id: string;
  filename: string;
  original_filename: string;
  document_type: string;
  mime_type: string;
  file_size_bytes: number;
  status: string;
  source_id: string;
  page_count?: number;
  duration_seconds?: number;
  language?: string;
  encrypted: boolean;
  created_at: string;
  completed_at?: string;
  error_message?: string;
}

export interface SearchResultItem {
  score: number;
  collection: string;
  document_id: string;
  text: string;
  chunk_index: number;
  original_filename: string;
  document_type: string;
  source_id: string;
}

export interface SearchResponse {
  query: string;
  total_results: number;
  embedding_model: string;
  results: SearchResultItem[];
  took_ms: number;
}

export const api = {
  // Health
  health: () => request<{ status: string }>('/health'),

  // Sources
  createSource: (source_type: string, source_value: string) =>
    request<Source>('/sources', {
      method: 'POST',
      body: JSON.stringify({ source_type, source_value }),
    }),

  generateAlias: (alias_prefix?: string) =>
    request<Source>('/sources/alias', {
      method: 'POST',
      body: JSON.stringify({ alias_prefix }),
    }),

  listSources: () => request<Source[]>('/sources'),

  // Upload
  uploadDocument: async (file: File, source_id: string) => {
    const form = new FormData();
    form.append('file', file);
    form.append('source_id', source_id);

    const res = await fetch(`${BASE}/documents/upload`, {
      method: 'POST',
      body: form,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    return res.json();
  },

  // Documents
  getDocument: (id: string) => request<DocRecord>(`/documents/${id}`),
  downloadDocument: (id: string) => `${BASE}/documents/${id}/download`,

  // Search
  search: (query: string, top_k = 10, document_types?: string[], source_id?: string) =>
    request<SearchResponse>('/search', {
      method: 'POST',
      body: JSON.stringify({ query, top_k, document_types, source_id }),
    }),
};
