import WidgetGrid, { WidgetDefinition } from '../components/dashboard/WidgetGrid';
import { SampleWidget } from '../components/dashboard/widgets';

const widgets: WidgetDefinition[] = [
  {
    id: 'sample',
    component: <SampleWidget />,
    defaultLayout: { i: 'sample', x: 0, y: 0, w: 4, h: 4 },
  },
];

export default function Dashboard() {
  return (
    <main className="h-full w-full overflow-auto p-4 bg-surface-secondary">
      <WidgetGrid widgets={widgets} />
    </main>
  );
}
