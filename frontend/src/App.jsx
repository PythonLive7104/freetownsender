import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import Layout from "./components/Layout";
import { Loader } from "./components/ui";
import Auth from "./pages/Auth";
import Dashboard from "./pages/Dashboard";
import { pageLoaders } from "./pageLoaders";

/* Pages are split into their own chunks and fetched the first time you visit them.
   Bundling all sixteen together meant every user downloaded and parsed the Proxies
   and Billing screens before the Dashboard could paint. Auth, Layout and Dashboard stay
   in the main bundle: they are needed immediately, and splitting the landing route would
   only add a round trip before first paint.

   Vite emits one small chunk per page and the browser caches each, so a page is
   fetched once and is instant on every later visit. */
const Mailboxes = lazy(pageLoaders["/mailboxes"]);
const AutoReply = lazy(pageLoaders["/auto-reply"]);
const Rules = lazy(pageLoaders["/rules"]);
const Configuration = lazy(pageLoaders["/configuration"]);
const Listeners = lazy(pageLoaders["/listeners"]);
const Placeholders = lazy(pageLoaders["/placeholders"]);
const Links = lazy(pageLoaders["/links"]);
const Attachments = lazy(pageLoaders["/attachments"]);
const Proxies = lazy(pageLoaders["/proxies"]);
const Telegram = lazy(pageLoaders["/telegram"]);
const Security = lazy(pageLoaders["/security"]);
const Team = lazy(pageLoaders["/team"]);
const Settings = lazy(pageLoaders["/settings"]);
const Billing = lazy(pageLoaders["/billing"]);

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <Loader label="Loading…" />;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function PublicOnly({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <Loader label="Loading…" />;
  if (user) return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<Loader label="Loading…" />}>
        <Routes>
          <Route path="/login" element={<PublicOnly><Auth mode="login" /></PublicOnly>} />
          <Route path="/signup" element={<PublicOnly><Auth mode="signup" /></PublicOnly>} />
          <Route element={<Protected><Layout /></Protected>}>
            <Route index element={<Dashboard />} />
            <Route path="mailboxes" element={<Mailboxes />} />
            <Route path="auto-reply" element={<AutoReply />} />
            <Route path="rules" element={<Rules />} />
            <Route path="configuration" element={<Configuration />} />
            <Route path="listeners" element={<Listeners />} />
            <Route path="placeholders" element={<Placeholders />} />
            <Route path="links" element={<Links />} />
            <Route path="attachments" element={<Attachments />} />
            <Route path="proxies" element={<Proxies />} />
            <Route path="team" element={<Team />} />
            <Route path="billing" element={<Billing />} />
            <Route path="security" element={<Security />} />
            <Route path="telegram" element={<Telegram />} />
            <Route path="settings" element={<Settings />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
