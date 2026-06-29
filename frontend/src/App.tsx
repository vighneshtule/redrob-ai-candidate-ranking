import { BrowserRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@/components/common/ThemeProvider";
import { AppLayout } from "@/components/layout/AppLayout";
import Dashboard from "@/pages/Dashboard";
import Candidates from "@/pages/Candidates";
import PipelineVisualization from "@/pages/PipelineVisualization";
import PlaceholderPage from "@/pages/PlaceholderPage";

const queryClient = new QueryClient();

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider defaultTheme="dark" storageKey="redrob-theme">
        <BrowserRouter>
          <AppLayout>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/pipeline" element={<PipelineVisualization />} />
              <Route path="/candidates" element={<Candidates />} />
              <Route path="/analytics" element={<PlaceholderPage title="Analytics & Insights" />} />
              <Route path="/benchmarks" element={<PlaceholderPage title="Performance Benchmarks" />} />
              <Route path="/settings" element={<PlaceholderPage title="System Settings" />} />
              <Route path="*" element={<PlaceholderPage title="404 - Not Found" />} />
            </Routes>
          </AppLayout>
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

export default App;
