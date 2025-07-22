import { useState } from "react";
import DashboardLayout from "@/layouts/DashboardLayout";
import { FolderOpen, Check, X, Plus, Loader2, Lightbulb } from "lucide-react";
import { useProjects } from "@/hooks/useProjects";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Project } from "@/types";

function ProjectCard({ project }: { project: Project }) {
  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-lg font-semibold">{project.name}</CardTitle>
        <div className="bg-blue-100 p-2 rounded-lg">
          <FolderOpen className="size-5 text-blue-600" />
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          Manually created project. More details can be added here.
        </p>
        {/* Progress bar can be added later */}
      </CardContent>
    </Card>
  );
}

export default function ProjectsPage() {
  const {
    projects,
    suggestions,
    isLoading,
    error,
    acceptSuggestion,
    rejectSuggestion,
    createProject,
  } = useProjects();
  const [isCreateDialogOpen, setCreateDialogOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  const handleCreateProject = async () => {
    if (!newProjectName.trim()) return;
    setIsCreating(true);
    try {
      await createProject(newProjectName);
      setNewProjectName("");
      setCreateDialogOpen(false);
    } catch (err) {
      // Error is already logged in the hook, maybe show a toast here
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="flex flex-1 flex-col gap-6 p-4 pt-0">
        <div className="flex items-center justify-between">
          <h1 className="text-3xl font-bold">Projects</h1>
          <Dialog open={isCreateDialogOpen} onOpenChange={setCreateDialogOpen}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="mr-2 size-4" />
                New Project
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Create New Project</DialogTitle>
                <DialogDescription>
                  Enter a name for your new project.
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label htmlFor="name" className="text-right">
                    Name
                  </Label>
                  <Input
                    id="name"
                    value={newProjectName}
                    onChange={(e) => setNewProjectName(e.target.value)}
                    className="col-span-3"
                    placeholder="e.g., LifeLog Frontend"
                  />
                </div>
              </div>
              <DialogFooter>
                <Button
                  type="submit"
                  onClick={handleCreateProject}
                  disabled={isCreating}
                >
                  {isCreating && <Loader2 className="mr-2 size-4 animate-spin" />}
                  Create Project
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>

        {error && (
          <div className="text-red-500 bg-red-100 p-4 rounded-md">
            Error: {error.message}
          </div>
        )}

        {suggestions.length > 0 && (
          <div>
            <h2 className="text-2xl font-semibold mb-4 flex items-center">
              <Lightbulb className="mr-2 text-yellow-500" /> Project Suggestions
            </h2>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {suggestions.map((suggestion) => (
                <Card key={suggestion.id} className="bg-muted/40">
                  <CardHeader>
                    <CardTitle className="text-lg">{suggestion.suggested_name}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm text-muted-foreground mb-4">
                      Suggested based on your activity.
                    </p>
                    <div className="flex justify-end gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => rejectSuggestion(suggestion.id)}
                      >
                        <X className="size-4" />
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => acceptSuggestion(suggestion.id)}
                      >
                        <Check className="size-4" />
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )}

        <div>
          <h2 className="text-2xl font-semibold mb-4">Your Projects</h2>
          {isLoading ? (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              <Skeleton className="h-36 w-full" />
              <Skeleton className="h-36 w-full" />
              <Skeleton className="h-36 w-full" />
            </div>
          ) : projects.length > 0 ? (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {projects.map((project) => (
                <ProjectCard key={project.id} project={project} />
              ))}
            </div>
          ) : (
            <div className="bg-muted/50 min-h-[20vh] flex-1 rounded-xl flex items-center justify-center">
              <p className="text-muted-foreground">
                No projects yet. Create one to get started!
              </p>
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
