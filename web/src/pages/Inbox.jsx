import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Inbox as InboxIcon, Loader2, X } from 'lucide-react';
import { inboxAPI } from '../services/api';

export default function Inbox() {
  const client = useQueryClient();
  const [labels, setLabels] = useState({});
  const [error, setError] = useState('');
  const { data: items = [], isLoading } = useQuery({ queryKey: ['inbox', 'pending'], queryFn: () => inboxAPI.list('pending'), refetchInterval: 15000 });
  const decide = useMutation({
    mutationFn: ({ item, decision }) => inboxAPI.decide(item.id, decision, item.kind === 'classification' ? { label: labels[item.id] || item.payload?.suggested_label } : {}),
    onSuccess: () => { setError(''); client.invalidateQueries({ queryKey: ['inbox'] }); client.invalidateQueries({ queryKey: ['captures'] }); },
    onError: (e) => setError(e.response?.data?.detail || e.message),
  });
  return <div className="max-w-5xl mx-auto space-y-7">
    <div><p className="text-sm font-semibold uppercase tracking-wider text-blue-600">Corrections and decisions</p><h1 className="text-3xl font-bold">Inbox</h1><p className="text-gray-600 mt-1">LifeLog stays quiet unless uncertainty or a consequential change needs you.</p></div>
    {error && <p className="bg-red-50 text-red-700 p-3 rounded-lg">{error}</p>}
    {isLoading ? <Loader2 className="animate-spin" /> : items.length === 0 ? <div className="card text-center text-gray-500"><InboxIcon className="mx-auto mb-3" /><p>You’re all caught up.</p></div> : <div className="space-y-4">{items.map((item) => <article key={item.id} className={`bg-white border rounded-xl p-5 ${item.consequential ? 'border-amber-400' : 'border-gray-200'}`}>
      <div className="flex justify-between gap-4"><div><div className="flex items-center gap-2"><h2 className="font-semibold text-lg">{item.title}</h2>{item.consequential && <span className="text-xs bg-amber-100 text-amber-800 rounded-full px-2 py-1">Consequential</span>}</div>{item.summary && <p className="text-gray-600 mt-1">{item.summary}</p>}</div><span className="text-xs text-gray-500 whitespace-nowrap">{item.kind.replaceAll('_', ' ')}</span></div>
      {item.kind === 'classification' && <input className="input-field mt-4" value={labels[item.id] ?? item.payload?.suggested_label ?? ''} onChange={(e) => setLabels({ ...labels, [item.id]: e.target.value })} aria-label="Classification label" />}
      <div className="flex flex-wrap gap-2 mt-4">{(item.choices?.length ? item.choices : [{ id: 'accept', label: 'Accept' }, { id: 'reject', label: 'Reject' }]).map((choice) => <button key={choice.id} className={choice.id === 'accept' ? 'btn-primary flex items-center gap-2' : 'btn-secondary flex items-center gap-2'} onClick={() => decide.mutate({ item, decision: choice.id })}>{choice.id === 'accept' && <Check size={16} />}{choice.id === 'reject' && <X size={16} />}{choice.label || choice.id}</button>)}</div>
    </article>)}</div>}
  </div>;
}
