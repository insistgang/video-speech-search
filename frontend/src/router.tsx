import { createBrowserRouter } from "react-router-dom";
import { AppLayout } from "./components/AppLayout";
import { RouteErrorBoundary } from "./components/RouteErrorBoundary";
import { ImportPage } from "./pages/ImportPage";
import { KeywordsPage } from "./pages/KeywordsPage";
import { ResultDetailPage } from "./pages/ResultDetailPage";
import { SearchPage } from "./pages/SearchPage";
import { TasksPage } from "./pages/TasksPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    errorElement: <RouteErrorBoundary />,
    children: [
      { index: true, element: <SearchPage /> },
      { path: "import", element: <ImportPage /> },
      { path: "tasks", element: <TasksPage /> },
      { path: "results/:frameId", element: <ResultDetailPage /> },
      { path: "keywords", element: <KeywordsPage /> }
    ]
  }
]);
