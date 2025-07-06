import { useState, useEffect, useCallback } from "react";
import {
  getProjects,
  getProjectSuggestions,
  acceptProjectSuggestion,
  rejectProjectSuggestion,
  createProject,
} from "@/api/client";
import type { Project, ProjectSuggestion } from "@/types";

export function useProjects() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [suggestions, setSuggestions] = useState<ProjectSuggestion[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchProjectsAndSuggestions = useCallback(async () => {
    try {
      setIsLoading(true);
      const [fetchedProjects, fetchedSuggestions] = await Promise.all([
        getProjects(),
        getProjectSuggestions("pending"),
      ]);
      setProjects(fetchedProjects);
      setSuggestions(fetchedSuggestions);
      setError(null);
    } catch (err) {
      setError(err as Error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProjectsAndSuggestions();
  }, [fetchProjectsAndSuggestions]);

  const handleAcceptSuggestion = async (suggestionId: string) => {
    try {
      await acceptProjectSuggestion(suggestionId);
      fetchProjectsAndSuggestions(); // Refresh data
    } catch (err) {
      console.error("Failed to accept suggestion:", err);
      // Optionally, update error state to show feedback to the user
    }
  };

  const handleRejectSuggestion = async (suggestionId: string) => {
    try {
      await rejectProjectSuggestion(suggestionId);
      fetchProjectsAndSuggestions(); // Refresh data
    } catch (err) {
      console.error("Failed to reject suggestion:", err);
    }
  };

  const handleCreateProject = async (name: string) => {
    try {
      await createProject({ name });
      fetchProjectsAndSuggestions(); // Refresh data
    } catch (err) {
      console.error("Failed to create project:", err);
      throw err; // Re-throw to be handled by the form
    }
  };

  return {
    projects,
    suggestions,
    isLoading,
    error,
    acceptSuggestion: handleAcceptSuggestion,
    rejectSuggestion: handleRejectSuggestion,
    createProject: handleCreateProject,
    refresh: fetchProjectsAndSuggestions,
  };
}