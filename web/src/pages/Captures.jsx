import { createElement, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Camera, FileUp, Loader2, Mic, NotebookPen, RefreshCw } from 'lucide-react';
import { capturesAPI, lifeAreasAPI } from '../services/api';

const statusStyle = {
  ready: 'bg-emerald-100 text-emerald-700',
  awaiting_review: 'bg-amber-100 text-amber-800',
  failed: 'bg-red-100 text-red-700',
  partially_ready: 'bg-blue-100 text-blue-700',
  processing: 'bg-violet-100 text-violet-700',
  preserved: 'bg-gray-100 text-gray-700',
};

export default function Captures() {
  const [mode, setMode] = useState('note');
  const [note, setNote] = useState('');
  const [intent, setIntent] = useState('');
  const [context, setContext] = useState('');
  const [error, setError] = useState('');
  const [lifeAreaIds, setLifeAreaIds] = useState([]);
  const [visibility, setVisibility] = useState('global');
  const inputRef = useRef(null);
  const client = useQueryClient();
  const { data: captures = [], isLoading } = useQuery({
    queryKey: ['captures'], queryFn: capturesAPI.list, refetchInterval: 10000,
  });
  const { data: lifeAreas = [] } = useQuery({ queryKey: ['life-areas'], queryFn: lifeAreasAPI.list });
  const privacy = () => ({
    visibility,
    allowed_area_ids: visibility === 'selected_areas' ? lifeAreaIds : [],
  });
  const refresh = () => client.invalidateQueries({ queryKey: ['captures'] });
  const noteMutation = useMutation({
    mutationFn: capturesAPI.createNote,
    onSuccess: () => { setNote(''); setError(''); refresh(); },
    onError: (e) => setError(e.response?.data?.detail || e.message),
  });
  const fileMutation = useMutation({
    mutationFn: capturesAPI.createFiles,
    onSuccess: () => { setError(''); refresh(); },
    onError: (e) => setError(e.response?.data?.detail || e.message),
  });

  const submitNote = (event) => {
    event.preventDefault();
    noteMutation.mutate({
      text: note, intent: intent || null,
      context_hints: context ? { context } : {},
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      life_area_ids: lifeAreaIds,
      privacy: privacy(),
    });
  };
  const upload = (event) => {
    const files = Array.from(event.target.files || []);
    if (!files.length) return;
    fileMutation.mutate({ files, kind: mode, intent, contextHints: context ? { context } : {}, lifeAreaIds, privacy: privacy() });
    event.target.value = '';
  };

  return (
    <div className="max-w-6xl mx-auto space-y-7">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wider text-blue-600">Remember something</p>
        <h1 className="text-3xl font-bold text-gray-900">Capture</h1>
        <p className="text-gray-600 mt-1">Save it now. LifeLog can organize and understand it afterward.</p>
      </div>

      <div className="card border border-gray-200 shadow-sm">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          {[
            ['note', NotebookPen, 'Write note'], ['photo', Camera, 'Add photos'],
            ['audio', Mic, 'Add recording'], ['file', FileUp, 'Add files'],
          ].map(([value, Icon, label]) => (
            <button key={value} onClick={() => setMode(value)}
              className={`p-4 rounded-xl border text-left transition ${mode === value ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-gray-300'}`}>
              {createElement(Icon, { size: 22, className: mode === value ? 'text-blue-600' : 'text-gray-500' })}
              <span className="block font-medium mt-2">{label}</span>
            </button>
          ))}
        </div>
        <div className="grid md:grid-cols-2 gap-4 mb-4">
          <input className="input-field" value={intent} onChange={(e) => setIntent(e.target.value)} placeholder="What is this? (optional)" />
          <input className="input-field" value={context} onChange={(e) => setContext(e.target.value)} placeholder="Context, e.g. Calculus 12 (optional)" />
        </div>
        <div className="grid md:grid-cols-2 gap-4 mb-4">
          <label className="text-sm font-medium text-gray-700">Life Areas
            <select multiple className="input-field mt-1 min-h-24" value={lifeAreaIds} onChange={(e) => setLifeAreaIds(Array.from(e.target.selectedOptions, (option) => option.value))}>
              {lifeAreas.map((area) => <option key={area.id} value={area.id}>{area.name}</option>)}
            </select>
            <span className="block text-xs text-gray-500 mt-1">Optional. A memory may be relevant to several areas.</span>
          </label>
          <label className="text-sm font-medium text-gray-700">Use in AI and recall
            <select className="input-field mt-1" value={visibility} onChange={(e) => setVisibility(e.target.value)}>
              <option value="global">Whole-life and selected-area views</option>
              <option value="selected_areas">Only the selected Life Areas</option>
              <option value="private">Preserve privately; exclude from scoped AI</option>
            </select>
          </label>
        </div>
        {mode === 'note' ? (
          <form onSubmit={submitNote}>
            <textarea className="input-field min-h-36" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Write anything you want LifeLog to remember…" required />
            <button className="btn-primary mt-4" disabled={noteMutation.isPending}>Save note</button>
          </form>
        ) : (
          <div className="border-2 border-dashed border-gray-300 rounded-xl p-9 text-center">
            <input ref={inputRef} type="file" multiple className="hidden" accept={mode === 'photo' ? 'image/*' : mode === 'audio' ? 'audio/*,video/*' : undefined} onChange={upload} />
            <FileUp className="mx-auto text-blue-600" />
            <p className="font-medium mt-3">Choose {mode === 'photo' ? 'photos' : mode === 'audio' ? 'recordings' : 'files'}</p>
            <p className="text-sm text-gray-500 mt-1">Originals are preserved before processing begins.</p>
            <button className="btn-primary mt-4" onClick={() => inputRef.current?.click()} disabled={fileMutation.isPending}>Choose files</button>
          </div>
        )}
        {error && <p className="mt-4 text-sm text-red-600">{error}</p>}
      </div>

      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xl font-semibold">Recent captures</h2>
          <button onClick={refresh} className="text-gray-500 hover:text-blue-600"><RefreshCw size={18} /></button>
        </div>
        {isLoading ? <Loader2 className="animate-spin" /> : captures.length === 0 ? (
          <div className="card text-center text-gray-500">Your captures will appear here.</div>
        ) : <div className="space-y-3">{captures.map((capture) => (
          <div key={capture.id} className="bg-white border border-gray-200 rounded-xl p-4 flex items-start justify-between gap-4">
            <div>
              <p className="font-medium">{capture.intent || capture.classification?.label || capture.kind}</p>
              <p className="text-sm text-gray-500 mt-1">{new Date(capture.captured_at).toLocaleString()} · {capture.kind}</p>
              {capture.text_content && <p className="text-sm text-gray-700 mt-2 line-clamp-2">{capture.text_content}</p>}
            </div>
            <span className={`px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap ${statusStyle[capture.status] || 'bg-gray-100 text-gray-700'}`}>
              {capture.status.replaceAll('_', ' ')}
            </span>
          </div>
        ))}</div>}
      </section>
    </div>
  );
}
