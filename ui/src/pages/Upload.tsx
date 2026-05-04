import { useState, useRef, useCallback } from 'react';
import { Upload, X, FileText, CheckCircle, AlertCircle, Sparkles, Loader2 } from 'lucide-react';
import { api, Source } from '../api';

export default function UploadPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [sourceId, setSourceId] = useState('');
  const [aliasPrefix, setAliasPrefix] = useState('');
  const [source, setSource] = useState<Source | null>(null);
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState<{ name: string; status: string; msg: string }[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = Array.from(e.dataTransfer.files);
    setFiles(prev => [...prev, ...dropped]);
  }, []);

  const removeFile = (idx: number) => {
    setFiles(prev => prev.filter((_, i) => i !== idx));
  };

  const generateAlias = async () => {
    try {
      const src = await api.generateAlias(aliasPrefix || undefined);
      setSource(src);
      setSourceId(src.id);
    } catch (err: any) {
      console.error(err);
    }
  };

  const registerSource = async () => {
    const type = sourceId.includes('@') ? 'email' : 'alias';
    const src = await api.createSource(type, sourceId);
    setSource(src);
  };

  const uploadAll = async () => {
    if (!source || files.length === 0) return;
    setUploading(true);
    const res: { name: string; status: string; msg: string }[] = [];

    for (const file of files) {
      try {
        const r = await api.uploadDocument(file, source.id);
        res.push({ name: file.name, status: r.status, msg: r.message });
      } catch (err: any) {
        res.push({ name: file.name, status: 'error', msg: err.message });
      }
    }

    setResults(res);
    setFiles([]);
    setUploading(false);
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  };

  return (
    <div className="max-w-2xl mx-auto py-12 px-4">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Upload Documenti</h1>
      <p className="text-gray-500 mb-8">
        Carica PDF, Word, immagini, audio, video, Markdown — Argos li indicizza tutti.
      </p>

      {/* Source attribution */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
        <h2 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
          <Sparkles size={16} className="text-argos-500" />
          Attribuzione Fonte
        </h2>

        {source ? (
          <div className="flex items-center gap-3 p-3 bg-green-50 border border-green-200 rounded-lg">
            <CheckCircle size={18} className="text-green-600" />
            <div>
              <span className="text-sm font-medium text-green-800">
                {source.source_type.toUpperCase()}
              </span>
              <span className="text-sm text-green-700 ml-2">{source.source_value}</span>
              <span className="text-xs text-green-600 ml-2">({source.id})</span>
            </div>
            <button
              onClick={() => { setSource(null); setSourceId(''); }}
              className="ml-auto text-green-600 hover:text-green-800"
            >
              <X size={16} />
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex gap-2">
              <input
                type="text"
                value={sourceId}
                onChange={e => setSourceId(e.target.value)}
                placeholder="Email, telefono o ID fonte..."
                className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-argos-500 focus:border-argos-500 outline-none"
              />
              <button
                onClick={registerSource}
                disabled={!sourceId.trim()}
                className="px-4 py-2 bg-argos-600 text-white rounded-lg text-sm font-medium hover:bg-argos-700 disabled:opacity-50 transition-colors"
              >
                Registra
              </button>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-400">oppure</span>
              <input
                type="text"
                value={aliasPrefix}
                onChange={e => setAliasPrefix(e.target.value)}
                placeholder="Prefisso alias..."
                className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm w-40 focus:ring-2 focus:ring-argos-500 focus:border-argos-500 outline-none"
              />
              <button
                onClick={generateAlias}
                className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200 transition-colors"
              >
                Genera Alias
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Drop zone */}
      <div
        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`
          bg-white rounded-xl border-2 border-dashed p-10 text-center cursor-pointer transition-colors mb-6
          ${dragOver ? 'border-argos-400 bg-argos-50' : 'border-gray-300 hover:border-gray-400'}
        `}
        onClick={() => fileInputRef.current?.click()}
      >
        <Upload size={40} className="mx-auto text-gray-400 mb-3" />
        <p className="text-gray-600 font-medium">Trascina i file qui</p>
        <p className="text-sm text-gray-400 mt-1">
          oppure clicca per selezionare · PDF, DOCX, JPG, MP4, MP3, MD, TXT...
        </p>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={e => {
            if (e.target.files) {
              setFiles(prev => [...prev, ...Array.from(e.target.files!)]);
            }
          }}
        />
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-700">
              {files.length} file{files.length > 1 ? 's' : ''} selezionati
            </h3>
            <button
              onClick={() => setFiles([])}
              className="text-xs text-gray-400 hover:text-gray-600"
            >
              Rimuovi tutti
            </button>
          </div>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {files.map((f, i) => (
              <div key={i} className="flex items-center gap-3 p-2 bg-gray-50 rounded-lg">
                <FileText size={18} className="text-gray-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-700 truncate">{f.name}</p>
                  <p className="text-xs text-gray-400">{formatSize(f.size)}</p>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); removeFile(i); }}
                  className="text-gray-400 hover:text-red-500"
                >
                  <X size={16} />
                </button>
              </div>
            ))}
          </div>
          <button
            onClick={uploadAll}
            disabled={!source || uploading}
            className="mt-4 w-full py-2.5 bg-argos-600 text-white rounded-lg text-sm font-medium hover:bg-argos-700 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
          >
            {uploading ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                Caricamento in corso...
              </>
            ) : (
              <>
                <Upload size={16} />
                Carica {files.length} file{files.length > 1 ? 's' : ''}
              </>
            )}
          </button>
        </div>
      )}

      {/* Results */}
      {results.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">Risultati</h3>
          <div className="space-y-2">
            {results.map((r, i) => (
              <div
                key={i}
                className={`flex items-center gap-2 p-2 rounded-lg text-sm ${
                  r.status === 'completed' ? 'bg-green-50 text-green-700' :
                  r.status === 'error' ? 'bg-red-50 text-red-700' :
                  'bg-yellow-50 text-yellow-700'
                }`}
              >
                {r.status === 'completed' ? <CheckCircle size={16} /> :
                 r.status === 'error' ? <AlertCircle size={16} /> :
                 <Loader2 size={16} className="animate-spin" />}
                <span className="font-medium">{r.name}</span>
                <span className="text-xs opacity-70 ml-auto">{r.msg}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
