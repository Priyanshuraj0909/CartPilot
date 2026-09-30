import React, { useEffect, useState } from "react";
import { Dashboard } from "./pages/Dashboard";

export const App: React.FC = () => {
  const [, setCurrentPath] = useState(window.location.pathname);

  useEffect(() => {
    const handlePopState = () => setCurrentPath(window.location.pathname);
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  // Both "/" and "/dashboard" render the CartPilot Dashboard as required by Phase 1
  return <Dashboard />;
};

export default App;
