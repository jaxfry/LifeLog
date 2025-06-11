import DashboardLayout from "@/layouts/DashboardLayout";
import { FolderOpen, Calendar, Users, MoreHorizontal } from "lucide-react";

export default function ProjectsPage() {
  return (
    <DashboardLayout>
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <div className="flex items-center justify-between">
          <h1 className="text-3xl font-bold">Projects</h1>
          <button className="bg-primary text-primary-foreground px-4 py-2 rounded-md hover:bg-primary/90 transition-colors">
            New Project
          </button>
        </div>
        
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {/* Project cards */}
          <div className="bg-card rounded-lg border p-6 hover:shadow-md transition-shadow">
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="bg-blue-100 p-2 rounded-lg">
                  <FolderOpen className="size-4 text-blue-600" />
                </div>
                <div>
                  <h3 className="font-semibold">LifeLog Frontend</h3>
                  <p className="text-sm text-muted-foreground">Web Application</p>
                </div>
              </div>
              <button className="text-muted-foreground hover:text-foreground">
                <MoreHorizontal className="size-4" />
              </button>
            </div>
            
            <p className="text-sm text-muted-foreground mb-4">
              Personal productivity tracking application with modern UI
            </p>
            
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <div className="flex items-center gap-1">
                <Calendar className="size-3" />
                <span>Due Dec 31</span>
              </div>
              <div className="flex items-center gap-1">
                <Users className="size-3" />
                <span>Solo</span>
              </div>
            </div>
            
            <div className="mt-4">
              <div className="w-full bg-muted rounded-full h-2">
                <div className="bg-blue-600 h-2 rounded-full" style={{ width: '75%' }}></div>
              </div>
              <p className="text-xs text-muted-foreground mt-1">75% complete</p>
            </div>
          </div>
          
          <div className="bg-card rounded-lg border p-6 hover:shadow-md transition-shadow">
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="bg-green-100 p-2 rounded-lg">
                  <FolderOpen className="size-4 text-green-600" />
                </div>
                <div>
                  <h3 className="font-semibold">API Backend</h3>
                  <p className="text-sm text-muted-foreground">Backend Service</p>
                </div>
              </div>
              <button className="text-muted-foreground hover:text-foreground">
                <MoreHorizontal className="size-4" />
              </button>
            </div>
            
            <p className="text-sm text-muted-foreground mb-4">
              RESTful API service for data management and user authentication
            </p>
            
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <div className="flex items-center gap-1">
                <Calendar className="size-3" />
                <span>Due Jan 15</span>
              </div>
              <div className="flex items-center gap-1">
                <Users className="size-3" />
                <span>Solo</span>
              </div>
            </div>
            
            <div className="mt-4">
              <div className="w-full bg-muted rounded-full h-2">
                <div className="bg-green-600 h-2 rounded-full" style={{ width: '45%' }}></div>
              </div>
              <p className="text-xs text-muted-foreground mt-1">45% complete</p>
            </div>
          </div>
          
          <div className="bg-card rounded-lg border p-6 hover:shadow-md transition-shadow">
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="bg-purple-100 p-2 rounded-lg">
                  <FolderOpen className="size-4 text-purple-600" />
                </div>
                <div>
                  <h3 className="font-semibold">Mobile App</h3>
                  <p className="text-sm text-muted-foreground">Mobile Application</p>
                </div>
              </div>
              <button className="text-muted-foreground hover:text-foreground">
                <MoreHorizontal className="size-4" />
              </button>
            </div>
            
            <p className="text-sm text-muted-foreground mb-4">
              Cross-platform mobile application for on-the-go tracking
            </p>
            
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <div className="flex items-center gap-1">
                <Calendar className="size-3" />
                <span>Due Feb 28</span>
              </div>
              <div className="flex items-center gap-1">
                <Users className="size-3" />
                <span>Solo</span>
              </div>
            </div>
            
            <div className="mt-4">
              <div className="w-full bg-muted rounded-full h-2">
                <div className="bg-purple-600 h-2 rounded-full" style={{ width: '20%' }}></div>
              </div>
              <p className="text-xs text-muted-foreground mt-1">20% complete</p>
            </div>
          </div>
        </div>
        
        {/* Additional projects content area */}
        <div className="bg-muted/50 min-h-[30vh] flex-1 rounded-xl flex items-center justify-center">
          <p className="text-muted-foreground">More projects and analytics will appear here</p>
        </div>
      </div>
    </DashboardLayout>
  );
}
