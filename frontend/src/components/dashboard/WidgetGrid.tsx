import type { ReactNode } from 'react';
import { useCallback, useEffect, useState } from 'react';
import GridLayout, { type Layout } from 'react-grid-layout';
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
    // Load layout from localStorage or use default
    const storedLayout = localStorage.getItem('dashboardLayout');
    const storedActiveWidgets = localStorage.getItem('dashboardActiveWidgets');
    
    let initialLayout: Layout[];
    let currentActiveWidgets: WidgetDefinition[] = widgets;

    if (storedLayout) {
      try {
        initialLayout = JSON.parse(storedLayout);
        if (storedActiveWidgets) {
          const activeWidgetIds = JSON.parse(storedActiveWidgets) as string[];
          // Filter available widgets based on stored IDs and ensure they still exist in the main widgets list
          currentActiveWidgets = widgets.filter(w => activeWidgetIds.includes(w.id));
          // Ensure layout only contains items for currently active widgets
          const activeLayoutItems = initialLayout.filter(l => activeWidgetIds.includes(l.i));
          // If an active widget from storage is not in the current layout, add its default layout
          activeWidgetIds.forEach(id => {
            if (!activeLayoutItems.find(l => l.i === id) && widgets.find(w => w.id === id)) {
              activeLayoutItems.push(widgets.find(w => w.id === id)!.defaultLayout);
            }
          });
          setLayout(activeLayoutItems);
        } else {
          // If no active widgets stored, assume all widgets are active with their default layouts
          setLayout(widgets.map(w => w.defaultLayout));
        }
      } catch {
        // Fallback to default if parsing fails
        currentActiveWidgets = widgets;
        setLayout(widgets.map(w => w.defaultLayout));
      }
    } else {
      // Default setup: all widgets active with their default layouts
      currentActiveWidgets = widgets;
      setLayout(widgets.map(w => w.defaultLayout));
    }
    setActiveWidgets(currentActiveWidgets);
  }, [widgets]);

  const handleLayoutChange = useCallback((newLayout: Layout[]) => {
    // Filter out layout items that don't correspond to an active widget
    const activeWidgetIds = activeWidgets.map(w => w.id);
    const filteredLayout = newLayout.filter(item => activeWidgetIds.includes(item.i));
    setLayout(filteredLayout);
  }, [activeWidgets]);

  useEffect(() => {
    localStorage.setItem('dashboardLayout', JSON.stringify(layout));
    localStorage.setItem('dashboardActiveWidgets', JSON.stringify(activeWidgets.map(w => w.id)));
  }, [layout, activeWidgets]);

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
            <Card className="h-full flex flex-col" variant={edit ? "outlined" : "elevated"}>
              {edit && (
                <button
                  className="absolute top-2 right-2 z-10 p-1 bg-red-500 text-white rounded-full hover:bg-red-600 transition-colors"
                  onClick={() => removeWidget(widget.id)}
                  aria-label="Remove widget"
                >
                  <X className="w-3 h-3" />
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
