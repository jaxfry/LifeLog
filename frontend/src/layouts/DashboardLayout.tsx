import { AppSidebar } from "@/components/app-sidebar";
import { Outlet } from "react-router-dom";
import { SidebarFooterProvider, useSidebarContext } from "@/context/SidebarContext";
import { SidebarProvider as SidebarUIProvider } from "@/components/ui/sidebar";

function Layout({ children }: { children?: React.ReactNode }) {
  const { sidebarFooter } = useSidebarContext();
  return (
    <div className="bg-background text-foreground flex min-h-screen w-full">
      <AppSidebar sidebarFooter={sidebarFooter} />
      <main className="flex-1 overflow-auto">
        {children ? children : <Outlet />}
      </main>
    </div>
  );
}

export default function DashboardLayout({ children }: { children?: React.ReactNode }) {
  return (
    <SidebarFooterProvider>
      <SidebarUIProvider>
        <Layout>{children}</Layout>
      </SidebarUIProvider>
    </SidebarFooterProvider>
  );
}
