import { AppSidebar } from "@/components/app-sidebar";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
} from "@/components/ui/breadcrumb";
import { Separator } from "@/components/ui/separator";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import React from "react";
import { useLocation } from "react-router-dom";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const location = useLocation();
  
  // Get the current page title from the pathname
  const getPageTitle = (pathname: string) => {
    switch (pathname) {
      case '/dashboard':
        return 'Dashboard';
      case '/timeline':
        return 'Timeline';
      case '/projects':
        return 'Projects';
      case '/insights':
        return 'Insights';
      default:
        return 'Dashboard';
    }
  };

  const pageTitle = getPageTitle(location.pathname);

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <header className="flex h-16 shrink-0 items-center gap-2 transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-12">
          <div className="flex items-center gap-2 px-4">
            <SidebarTrigger className="-ml-1" />
            <Separator
              orientation="vertical"
              className="mr-2 data-[orientation=vertical]:h-4"
            />
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem className="hidden md:block">
                  <BreadcrumbLink href="/dashboard">
                    {pageTitle}
                  </BreadcrumbLink>
                </BreadcrumbItem>
                {/* Further breadcrumb items can be added by child pages or a more dynamic system */}
              </BreadcrumbList>
            </Breadcrumb>
          </div>
        </header>
        {children} {/* Page content will be rendered here */}
      </SidebarInset>
    </SidebarProvider>
  );
}
