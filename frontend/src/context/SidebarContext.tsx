import { createContext, useContext, useState, ReactNode } from 'react';

interface SidebarContextType {
  setSidebarFooter: (content: ReactNode) => void;
  sidebarFooter: ReactNode;
}

const SidebarContext = createContext<SidebarContextType | undefined>(undefined);

export const SidebarFooterProvider = ({ children }: { children: ReactNode }) => {
  const [sidebarFooter, setSidebarFooter] = useState<ReactNode>(null);

  return (
    <SidebarContext.Provider value={{ sidebarFooter, setSidebarFooter }}>
      {children}
    </SidebarContext.Provider>
  );
};

export const useSidebarContext = () => {
  const context = useContext(SidebarContext);
  if (!context) {
    throw new Error('useSidebarContext must be used within a SidebarProvider');
  }
  return context;
};
