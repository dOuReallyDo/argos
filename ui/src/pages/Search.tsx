import { useState } from 'react';
import { Search as SearchIcon, FileText, Image, Music, Video, Clock, Loader2 } from 'lucide-react';
import { api, SearchResultItem } from '../api';

const typeIcons: Record<string, React.ReactNode> = {
  pdf: <FileText size={14} />,
  word: <FileText size={14} />,
  text: <FileText size={14} />,
  markdown: <FileText size={14} />,
  excel: <FileText size={14} />,
  powerpoint: <FileText size={14} />,
  image: <Image size={14} />,
  audio: <Music size={14} />,
  video: <Video size={14} />,
};

const typeLabels: Record<string, string> = {
  pdf: 'PDF', word: 'Word', text: 'Testo', markdown: 'Markdown',
  image: 'Immagine', audio: 'Audio', video: 'Video',
  excel: 'Excel', powerpoint: 'PowerPoint',
};

const typeFilters = ['pdf', 'word', 'text', 'markdown', 'image', 'audio', 'video'];

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [topK, setTopK] = useState(10);
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [tookMs, setTookMs] = useState(0);
  const [model, setModel] = useState('');

  const doSearch = async () => {
    if (!query.trim()) return;
    setSearching(true);
    try {
      const r = await api.search(
        query, topK,
        selectedTypes.length > 0 ? selectedTypes : undefined
      );
      setResults(r.results);
      setTookMs(r.took_ms);
      setModel(r.embedding_model);
    } catch (err: any) {
      console.error(err);
      setResults([]);
    }
    setSearching(false);
  };

  const toggleType = (t: string) => {
    setSelectedTypes(prev =>
      prev.includes(t) ? prev.filter(x => x !== t) : [...prev, t]
    );
  };

  const highlightText = (text: string, q: string) => {
    if (!q) return text;
    const idx = text.toLowerCase().indexOf(q.toLowerCase());
    if (idx === -1) return text;

    const before = text.slice(Math.max(0, idx - 40), idx);
    const match = text.slice(idx, idx + q.length);
    const after = text.slice(idx + q.length, idx + q.length + 120);

    return (
      <>
        {idx > 40 && '...'}
        {before}
        <mark className="bg-yellow-200 rounded px-0.5">{match}</mark>
        {after}
        {text.length > idx + q.length + 120 && '...'}
      </>
    );
  };

  return (
    <div className="max-w-3xl mx-auto py-12 px-4">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Ricerca Semantica</h1>
      <p className="text-gray-500 mb-8">
        Cerca nel contenuto dei tuoi documenti — testo, immagini, audio e video.
      </p>

      {/* Search bar */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-4 shadow-sm">
        <div className="flex gap-2">
          <div className="flex-1 relative">
            <SearchIcon size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && doSearch()}
              placeholder="Cerca nei documenti..."
              className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-argos-500 focus:border-argos-500 outline-none"
            />
          </div>
          <button
            onClick={doSearch}
            disabled={!query.trim() || searching}
            className="px-6 py-3 bg-argos-600 text-white rounded-lg text-sm font-medium hover:bg-argos-700 disabled:opacity-50 transition-colors flex items-center gap-2"
          >
            {searching ? <Loader2 size={16} className="animate-spin" /> : <SearchIcon size={16} />}
            Cerca
          </button>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-2 mt-3 flex-wrap">
          <span className="text-xs text-gray-400 mr-1">Filtra:</span>
          {typeFilters.map(t => (
            <button
              key={t}
              onClick={() => toggleType(t)}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                selectedTypes.includes(t)
                  ? 'bg-argos-100 text-argos-700'
                  : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
              }`}
            >
              {typeIcons[t]}
              {typeLabels[t]}
            </button>
          ))}
          <div className="ml-auto flex items-center gap-2">
            <label className="text-xs text-gray-400">Top-K:</label>
            <select
              value={topK}
              onChange={e => setTopK(Number(e.target.value))}
              className="text-xs border border-gray-200 rounded px-2 py-1 outline-none"
            >
              {[5, 10, 20, 50].map(n => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Metadata */}
      {model && (
        <div className="flex items-center gap-4 text-xs text-gray-400 mb-4 px-1">
          <span className="flex items-center gap-1">
            <Clock size={12} /> {tookMs.toFixed(1)}ms
          </span>
          <span>·</span>
          <span>Model: {model}</span>
          <span>·</span>
          <span>{results.length} risultati</span>
        </div>
      )}

      {/* Results */}
      <div className="space-y-3">
        {results.map((r, i) => (
          <div
            key={i}
            className="bg-white rounded-xl border border-gray-200 p-4 hover:shadow-md transition-shadow"
          >
            <div className="flex items-start justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                  r.document_type === 'image' ? 'bg-purple-100 text-purple-700' :
                  r.document_type === 'audio' ? 'bg-orange-100 text-orange-700' :
                  r.document_type === 'video' ? 'bg-red-100 text-red-700' :
                  'bg-blue-100 text-blue-700'
                }`}>
                  {typeIcons[r.document_type]}
                  {typeLabels[r.document_type] || r.document_type}
                </span>
                <span className="text-sm font-medium text-gray-800 truncate max-w-md">
                  {r.original_filename}
                </span>
              </div>
              <span className="text-xs text-gray-400 font-mono">
                {(r.score * 100).toFixed(1)}%
              </span>
            </div>
            <p className="text-sm text-gray-600 leading-relaxed">
              {highlightText(r.text, query)}
            </p>
            <div className="flex items-center gap-2 mt-2 text-xs text-gray-400">
              <span>Chunk #{r.chunk_index}</span>
              <span>·</span>
              <span className="font-mono">doc:{r.document_id.slice(0, 8)}</span>
              <span>·</span>
              <span>src:{r.source_id.slice(0, 8)}</span>
            </div>
          </div>
        ))}

        {!searching && results.length === 0 && query && (
          <div className="text-center py-16 text-gray-400">
            <SearchIcon size={48} className="mx-auto mb-3 opacity-30" />
            <p>Nessun risultato trovato</p>
            <p className="text-sm mt-1">Prova con parole chiave diverse</p>
          </div>
        )}

        {!query && (
          <div className="text-center py-16 text-gray-400">
            <SearchIcon size={48} className="mx-auto mb-3 opacity-30" />
            <p>Inserisci una query e premi Cerca</p>
            <p className="text-sm mt-1">
              La ricerca semantica capisce il significato, non solo le parole esatte
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
