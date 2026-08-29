import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, Pause, Play, Plug, RefreshCw, Unplug } from 'lucide-react';
import { extensionsAPI, lifeAreasAPI, sourcesAPI } from '../services/api';

export default function Sources() {
  const client = useQueryClient();
  const [form, setForm] = useState({ extension_id: '', name: '', base_url: '', token: '', schedule_cron: '', life_area_ids: [] });
  const [error, setError] = useState('');
  const { data: sources = [], isLoading } = useQuery({ queryKey: ['sources'], queryFn: sourcesAPI.list });
  const { data: extensions = [] } = useQuery({ queryKey: ['extensions'], queryFn: extensionsAPI.getExtensions });
  const { data: lifeAreas = [] } = useQuery({ queryKey: ['life-areas'], queryFn: lifeAreasAPI.list });
  const collectors = extensions.filter((item) => item.is_active && (item.config?.capabilities || []).includes('collector'));
  const refresh = () => client.invalidateQueries({ queryKey: ['sources'] });
  const create = useMutation({
    mutationFn: sourcesAPI.create,
    onSuccess: () => { setForm({ extension_id: '', name: '', base_url: '', token: '', schedule_cron: '', life_area_ids: [] }); setError(''); refresh(); },
    onError: (e) => setError(e.response?.data?.detail || e.message),
  });
  const submit = (event) => {
    event.preventDefault();
    create.mutate({
      extension_id: form.extension_id, name: form.name,
      config: form.base_url ? { base_url: form.base_url } : {},
      schedule_cron: form.schedule_cron || null,
      secrets: form.token ? { access_token: form.token } : {},
      life_area_ids: form.life_area_ids,
    });
  };
  const act = async (fn) => { try { await fn(); setError(''); refresh(); } catch (e) { setError(e.response?.data?.detail || e.message); } };

  return (
    <div className="max-w-6xl mx-auto space-y-7">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wider text-blue-600">Connected memory</p>
        <h1 className="text-3xl font-bold">Sources</h1>
        <p className="text-gray-600 mt-1">Connect places where your life data already exists.</p>
      </div>
      <form onSubmit={submit} className="card border border-gray-200 shadow-sm">
        <h2 className="font-semibold text-lg mb-4">Add a source</h2>
        {collectors.length === 0 ? <p className="text-sm text-amber-700 bg-amber-50 p-3 rounded-lg">Install a collector extension before adding a source.</p> : (
          <div className="grid md:grid-cols-2 gap-4">
            <select className="input-field" value={form.extension_id} onChange={(e) => setForm({ ...form, extension_id: e.target.value })} required>
              <option value="">Choose a source type…</option>
              {collectors.map((item) => <option key={item.id} value={item.id}>{item.config?.name || item.id}</option>)}
            </select>
            <input className="input-field" placeholder="Connection name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            <input className="input-field" placeholder="Service URL (optional)" value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} />
            <input className="input-field" type="password" autoComplete="new-password" placeholder="Access token (stored encrypted)" value={form.token} onChange={(e) => setForm({ ...form, token: e.target.value })} />
            <input className="input-field" placeholder="Cron schedule, e.g. */15 * * * *" value={form.schedule_cron} onChange={(e) => setForm({ ...form, schedule_cron: e.target.value })} />
            <select multiple className="input-field min-h-20" value={form.life_area_ids} onChange={(e) => setForm({ ...form, life_area_ids: Array.from(e.target.selectedOptions, (option) => option.value) })}>
              {lifeAreas.map((area) => <option key={area.id} value={area.id}>{area.name}</option>)}
            </select>
            <button className="btn-primary" disabled={create.isPending}>{create.isPending ? 'Connecting…' : 'Connect source'}</button>
          </div>
        )}
        {error && <p className="text-sm text-red-600 mt-4">{error}</p>}
      </form>

      <section>
        <h2 className="text-xl font-semibold mb-3">Your sources</h2>
        {isLoading ? <Loader2 className="animate-spin" /> : sources.length === 0 ? (
          <div className="card text-center"><Plug className="mx-auto text-gray-400 mb-3" /><p className="text-gray-600">No sources connected yet.</p></div>
        ) : <div className="grid md:grid-cols-2 gap-4">{sources.map((source) => (
          <article key={source.id} className="bg-white border border-gray-200 rounded-xl p-5">
            <div className="flex justify-between gap-4">
              <div><h3 className="font-semibold">{source.name}</h3><p className="text-sm text-gray-500">{source.extension_id}</p></div>
              <span className={`text-xs px-2.5 py-1 rounded-full h-fit ${source.status === 'error' ? 'bg-red-100 text-red-700' : source.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-700'}`}>{source.status}</span>
            </div>
            <p className="text-sm text-gray-600 mt-4">Last sync: {source.last_sync_completed_at ? new Date(source.last_sync_completed_at).toLocaleString() : 'Never'}</p>
            {source.last_sync_error && <p className="text-sm text-red-600 mt-2 line-clamp-2">{source.last_sync_error}</p>}
            <div className="flex flex-wrap gap-2 mt-4">
              <button className="btn-secondary flex items-center gap-2 text-sm" onClick={() => act(() => sourcesAPI.sync(source.id))}><RefreshCw size={15} /> Sync now</button>
              <button className="btn-secondary flex items-center gap-2 text-sm" onClick={() => act(() => sourcesAPI.update(source.id, { is_active: !source.is_active }))}>{source.is_active ? <Pause size={15} /> : <Play size={15} />} {source.is_active ? 'Pause' : 'Resume'}</button>
              <button className="px-3 py-2 text-sm text-red-600 hover:bg-red-50 rounded-lg flex items-center gap-2" onClick={() => act(() => sourcesAPI.disconnect(source.id))}><Unplug size={15} /> Disconnect</button>
            </div>
          </article>
        ))}</div>}
      </section>
    </div>
  );
}
