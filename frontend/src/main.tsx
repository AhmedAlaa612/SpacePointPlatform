import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import "@fontsource-variable/inter";
import "@fontsource/outfit/400.css";
import "@fontsource/outfit/500.css";
import "@fontsource/outfit/700.css";
import "@fontsource/outfit/900.css";
import "./index.css";
import { router } from "./router";
import { AuthProvider } from "./context/AuthContext";

// Apply persisted theme before first paint to avoid a flash.
// Dark (the instructors "space" theme) is the default; only an explicit
// stored "light" preference opts out.
const storedTheme = localStorage.getItem("theme");
if (storedTheme !== "light") {
  document.documentElement.classList.add("dark");
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
