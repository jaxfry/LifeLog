import { useNavigate } from "react-router-dom";
import { useEffect } from "react";

export default function Home() {
  const navigate = useNavigate();
  
  useEffect(() => {
    // Redirect to the sample date as shown in the image (May 24, 2025)
    navigate(`/day/2025-05-24`);
  }, [navigate]);
  
  // This will only show briefly before the redirect
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="text-xl font-semibold text-gray-500">
        Loading TimeFlow...
      </div>
    </div>
  );
}