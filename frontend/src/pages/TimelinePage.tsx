import DashboardLayout from "@/layouts/DashboardLayout";

export default function TimelinePage() {
  return (
    <DashboardLayout>
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <div className="flex items-center justify-between">
          <h1 className="text-3xl font-bold">Timeline</h1>
        </div>
        
        <div className="flex flex-col gap-4">
          {/* Timeline entries container */}
          <div className="bg-card rounded-lg border p-6">
            <h2 className="text-xl font-semibold mb-4">Recent Activities</h2>
            
            {/* Sample timeline entries */}
            <div className="space-y-4">
              <div className="flex items-start gap-4 p-4 bg-muted/50 rounded-lg">
                <div className="w-2 h-2 bg-primary rounded-full mt-2"></div>
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <h3 className="font-medium">Project Meeting</h3>
                    <span className="text-sm text-muted-foreground">2 hours ago</span>
                  </div>
                  <p className="text-sm text-muted-foreground mt-1">
                    Discussed project milestones and upcoming deadlines
                  </p>
                </div>
              </div>
              
              <div className="flex items-start gap-4 p-4 bg-muted/50 rounded-lg">
                <div className="w-2 h-2 bg-primary rounded-full mt-2"></div>
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <h3 className="font-medium">Code Review</h3>
                    <span className="text-sm text-muted-foreground">4 hours ago</span>
                  </div>
                  <p className="text-sm text-muted-foreground mt-1">
                    Reviewed pull request for new feature implementation
                  </p>
                </div>
              </div>
              
              <div className="flex items-start gap-4 p-4 bg-muted/50 rounded-lg">
                <div className="w-2 h-2 bg-primary rounded-full mt-2"></div>
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <h3 className="font-medium">Documentation Update</h3>
                    <span className="text-sm text-muted-foreground">Yesterday</span>
                  </div>
                  <p className="text-sm text-muted-foreground mt-1">
                    Updated API documentation with new endpoints
                  </p>
                </div>
              </div>
            </div>
          </div>
          
          {/* Additional timeline content */}
          <div className="bg-muted/50 min-h-[50vh] flex-1 rounded-xl flex items-center justify-center">
            <p className="text-muted-foreground">More timeline content will appear here</p>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
