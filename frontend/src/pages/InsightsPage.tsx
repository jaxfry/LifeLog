import DashboardLayout from "@/layouts/DashboardLayout";
import { TrendingUp, Clock, Target, Activity } from "lucide-react";

export default function InsightsPage() {
  return (
    <DashboardLayout>
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <div className="flex items-center justify-between">
          <h1 className="text-3xl font-bold">Insights</h1>
          <select className="border rounded-md px-3 py-2 text-sm">
            <option>Last 7 days</option>
            <option>Last 30 days</option>
            <option>Last 3 months</option>
          </select>
        </div>
        
        {/* Key metrics */}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <div className="bg-card rounded-lg border p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Total Hours</p>
                <p className="text-2xl font-bold">47.5h</p>
              </div>
              <div className="bg-blue-100 p-3 rounded-lg">
                <Clock className="size-5 text-blue-600" />
              </div>
            </div>
            <div className="flex items-center gap-1 mt-2 text-sm">
              <TrendingUp className="size-3 text-green-500" />
              <span className="text-green-500">+12%</span>
              <span className="text-muted-foreground">from last week</span>
            </div>
          </div>
          
          <div className="bg-card rounded-lg border p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Completed Tasks</p>
                <p className="text-2xl font-bold">23</p>
              </div>
              <div className="bg-green-100 p-3 rounded-lg">
                <Target className="size-5 text-green-600" />
              </div>
            </div>
            <div className="flex items-center gap-1 mt-2 text-sm">
              <TrendingUp className="size-3 text-green-500" />
              <span className="text-green-500">+8%</span>
              <span className="text-muted-foreground">from last week</span>
            </div>
          </div>
          
          <div className="bg-card rounded-lg border p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Productivity Score</p>
                <p className="text-2xl font-bold">87%</p>
              </div>
              <div className="bg-purple-100 p-3 rounded-lg">
                <Activity className="size-5 text-purple-600" />
              </div>
            </div>
            <div className="flex items-center gap-1 mt-2 text-sm">
              <TrendingUp className="size-3 text-green-500" />
              <span className="text-green-500">+5%</span>
              <span className="text-muted-foreground">from last week</span>
            </div>
          </div>
          
          <div className="bg-card rounded-lg border p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Active Projects</p>
                <p className="text-2xl font-bold">3</p>
              </div>
              <div className="bg-orange-100 p-3 rounded-lg">
                <Target className="size-5 text-orange-600" />
              </div>
            </div>
            <div className="flex items-center gap-1 mt-2 text-sm">
              <span className="text-muted-foreground">Same as last week</span>
            </div>
          </div>
        </div>
        
        {/* Charts and analytics */}
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="bg-card rounded-lg border p-6">
            <h3 className="text-lg font-semibold mb-4">Weekly Activity</h3>
            <div className="bg-muted/50 h-64 rounded-lg flex items-center justify-center">
              <p className="text-muted-foreground">Activity chart will be displayed here</p>
            </div>
          </div>
          
          <div className="bg-card rounded-lg border p-6">
            <h3 className="text-lg font-semibold mb-4">Project Distribution</h3>
            <div className="bg-muted/50 h-64 rounded-lg flex items-center justify-center">
              <p className="text-muted-foreground">Project distribution chart will be displayed here</p>
            </div>
          </div>
        </div>
        
        {/* Time tracking insights */}
        <div className="bg-card rounded-lg border p-6">
          <h3 className="text-lg font-semibold mb-4">Time Breakdown</h3>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-3 h-3 bg-blue-500 rounded-full"></div>
                <span>Development</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-32 bg-muted rounded-full h-2">
                  <div className="bg-blue-500 h-2 rounded-full" style={{ width: '65%' }}></div>
                </div>
                <span className="text-sm text-muted-foreground w-12">65%</span>
              </div>
            </div>
            
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-3 h-3 bg-green-500 rounded-full"></div>
                <span>Meetings</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-32 bg-muted rounded-full h-2">
                  <div className="bg-green-500 h-2 rounded-full" style={{ width: '20%' }}></div>
                </div>
                <span className="text-sm text-muted-foreground w-12">20%</span>
              </div>
            </div>
            
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-3 h-3 bg-purple-500 rounded-full"></div>
                <span>Planning</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-32 bg-muted rounded-full h-2">
                  <div className="bg-purple-500 h-2 rounded-full" style={{ width: '15%' }}></div>
                </div>
                <span className="text-sm text-muted-foreground w-12">15%</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
