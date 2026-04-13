import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { AppLayout } from "../../components/AppLayout";
import { SearchPage } from "../SearchPage";

test("renders navigation labels", () => {
  const router = createMemoryRouter(
    [
      {
        path: "/",
        element: <AppLayout />,
        children: [{ index: true, element: <SearchPage /> }]
      }
    ],
    { initialEntries: ["/"] }
  );

  render(
    <RouterProvider router={router} />
  );

  expect(screen.getByRole("link", { name: "检索" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "任务" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "词库" })).toBeInTheDocument();
});
