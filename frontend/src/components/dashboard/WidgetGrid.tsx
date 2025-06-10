import { ReactNode, useCallback, useEffect, useState } from 'react';
import GridLayout, { Layout } from 'react-grid-layout';
import { Plus, X } from 'lucide-react';
import { Button, Card } from '../ui';

export interface WidgetDefinition {
  id: string;
  component: ReactNode;
  defaultLayout: Layout;
}

interface WidgetGridProps {
  widgets: WidgetDefinition[];
}

export default function WidgetGrid({ widgets }: WidgetGridProps) {
  const [layout, setLayout] = useState<Layout[]>([]);
  const [activeWidgets, setActiveWidgets] = useState<WidgetDefinition[]>(widgets);
  const [edit, setEdit] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem('dashboardLayout');
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        setLayout(parsed);
      } catch {
        // ignore
      }
    } else {
      setLayout(widgets.map(w => w.defaultLayout));
    }
  }, [widgets]);

  const handleLayoutChange = useCallback((l: Layout[]) => {
    setLayout(l);
  }, []);

  useEffect(() => {
    localStorage.setItem('dashboardLayout', JSON.stringify(layout));
  }, [layout]);

  const removeWidget = (id: string) => {
    setActiveWidgets(ws => ws.filter(w => w.id !== id));
    setLayout(l => l.filter(item => item.i !== id));
  };

  return (
    <div className="relative">
      <GridLayout
        className="layout"
        layout={layout}
        cols={12}
        rowHeight={30}
        width={1200}
        margin={[16, 16]}
        isDraggable={edit}
        isResizable={edit}
        onLayoutChange={handleLayoutChange}
      >
        {activeWidgets.map(widget => (
          <div key={widget.id} className="h-full">
            <Card className="h-full">
              {edit && (
                <button
                  className="absolute top-2 right-2 text-neutral-500 hover:text-neutral-800"
                  onClick={() => removeWidget(widget.id)}
                >
                  <X className="w-4 h-4" />
                </button>
              )}
              {widget.component}
            </Card>
          </div>
        ))}
      </GridLayout>
      <Button
        variant="primary"
        size="icon"
        className="fixed bottom-4 right-4 rounded-full"
        onClick={() => setEdit(e => !e)}
        aria-label={edit ? 'Done editing' : 'Edit dashboard'}
      >
        {edit ? <X className="w-5 h-5" /> : <Plus className="w-5 h-5" />}
      </Button>
    </div>
  );
}
