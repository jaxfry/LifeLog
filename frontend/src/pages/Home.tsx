import { useNavigate } from "react-router-dom";
import { useEffect } from "react";

export default function Home() {
  const navigate = useNavigate();
  
  useEffect(() => {
    // Redirect to a date with real data (May 22, 2025)
    navigate(`/day/2025-05-22`);
  }, [navigate]);
  
  // This will only show briefly before the redirect
  return (
    <div className="h-full w-full bg-background-default flex items-center justify-center overflow-hidden">
      <div className="text-xl font-semibold text-text-secondary">
        Loading TimeFlow...
      </div>
    </div>
  );
}