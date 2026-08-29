import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Layers3, Loader2, Plus } from 'lucide-react';
import { lifeAreasAPI } from '../services/api';

export default function LifeAreas() {
  const client = useQueryClient();
  const [form, setForm] = useState({ name: '', description: '', color: '#2563eb' });
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState('');
  const { data: areas = [], isLoading } = useQuery({ queryKey: ['life-areas'], queryFn: lifeAreasAPI.list });
  const { data: templates = [] } = useQuery({ queryKey: ['life-area-templates'], queryFn: lifeAreasAPI.templates });
  const { data: memories = [], isLoading: memoriesLoading } = useQuery({
    queryKey: ['life-area-memories', selected],
    queryFn: () => lifeAreasAPI.memories(selected),
    enabled: Boolean(selected),
  });
  const create = useMutation({
    mutationFn: lifeAreasAPI.create,
    onSuccess: (area) => {
      setForm({ name: '', description: '', color: '#2563eb' });
      setSelected(area.id);
      setError('');
      client.invalidateQueries({ queryKey: ['life-areas'] });
    },
    onError: (e) => setError(e.response?.data?.detail || e.message),
  });

  return <div className="max-w-6xl mx-auto space-y-7">
    <div>
      <p className="text-sm font-semibold uppercase tracking-wider text-blue-600">One memory, many views</p>
      <h1 className="text-3xl font-bold text-gray-900">Life Areas</h1>
      <p className="text-gray-600 mt-1">Create useful lenses such as School, Health, Work, or Family. Memories stay unified and can belong to more than one area.</p>
    </div>
    <form className="card border border-gray-200 grid md:grid-cols-[1fr_2fr_auto_auto] gap-3 items-end" onSubmit={(event) => { event.preventDefault(); create.mutate(form); }}>
      <label className="text-sm font-medium">Name<input className="input-field mt-1" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="School" required /></label>
      <label className="text-sm font-medium">Purpose<input className="input-field mt-1" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Classes, assignments, studying, and learning" /></label>
      <label className="text-sm font-medium">Color<input type="color" className="block h-11 w-16 mt-1" value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} /></label>
      <button className="btn-primary flex items-center gap-2" disabled={create.isPending}><Plus size={17} /> Add area</button>
      {error && <p className="text-sm text-red-600 md:col-span-4">{error}</p>}
    </form>
    {templates.length > 0 && <section><h2 className="font-semibold mb-2">Suggested by your sources</h2><div className="flex flex-wrap gap-2">{templates.filter((template) => !areas.some((area) => area.slug === template.slug)).map((template) => <button key={`${template.extension_id}:${template.slug}`} className="btn-secondary text-sm" onClick={() => create.mutate({
      name: template.name,
      slug: template.slug,
      description: template.description || '',
      icon: template.icon || null,
      color: template.color || '#2563eb',
      definition: {
        recognition_hints: template.recognition_hints || [],
        vocabulary: template.vocabulary || {},
        cards: template.cards || [],
        suggested_questions: template.suggested_questions || [],
        policies: template.policies || {},
        contributed_by: template.extension_id,
      },
    })}>Use {template.name}</button>)}</div></section>}
    {isLoading ? <Loader2 className="animate-spin" /> : areas.length === 0 ? <div className="card text-center text-gray-500"><Layers3 className="mx-auto mb-3" />Create your first Life Area. Nothing is copied or siloed.</div> : <div className="grid lg:grid-cols-[320px_1fr] gap-5">
      <div className="space-y-2">{areas.map((area) => <button key={area.id} onClick={() => setSelected(area.id)} className={`w-full text-left bg-white border rounded-xl p-4 ${selected === area.id ? 'border-blue-500 ring-2 ring-blue-100' : 'border-gray-200'}`}>
        <div className="flex items-center gap-3"><span className="w-3 h-3 rounded-full" style={{ backgroundColor: area.color || '#6b7280' }} /><span className="font-semibold">{area.name}</span></div>
        {area.description && <p className="text-sm text-gray-600 mt-2">{area.description}</p>}
      </button>)}</div>
      <div className="card border border-gray-200">
        {!selected ? <p className="text-gray-500">Choose an area to see its memories.</p> : memoriesLoading ? <Loader2 className="animate-spin" /> : memories.length === 0 ? <p className="text-gray-500">No relevant memories yet. Select this area while capturing, or let recognition rules connect future memories.</p> : <div className="space-y-3">{memories.map((memory) => <article key={memory.id} className="border-b border-gray-100 pb-3 last:border-0"><p className="font-medium">{memory.title || memory.source_type.replaceAll('_', ' ')}</p><p className="text-sm text-gray-600 mt-1 line-clamp-3">{memory.content}</p></article>)}</div>}
      </div>
    </div>}
  </div>;
}
