import type { ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { Home } from "./screens/Home";
import { Items } from "./screens/Items";
import { Processing } from "./screens/Processing";
import { PublicShop } from "./screens/PublicShop";
import { Record } from "./screens/Record";
import { Review } from "./screens/Review";
import { Settings } from "./screens/Settings";
import { Setup } from "./screens/Setup";
import { SignIn } from "./screens/SignIn";
import { VideoDetail } from "./screens/VideoDetail";
import { Videos } from "./screens/Videos";
import { SessionProvider, useSession } from "./session";

function Guard({ children }: { children: ReactElement }) {
  const { me, loading } = useSession();
  const { t } = useTranslation();
  if (loading) return <p className="content muted">{t("app.loading")}</p>;
  if (!me) return <Navigate to="/signin" replace />;
  if (!me.workspace.consent_account || !me.workspace.whatsapp) return <Navigate to="/setup" replace />;
  return children;
}

export function App() {
  return (
    <BrowserRouter>
      <SessionProvider>
        <Routes>
          <Route path="/signin" element={<SignIn />} />
          <Route path="/setup" element={<Setup />} />
          <Route path="/s/:slug" element={<PublicShop />} />
          <Route path="/s/:slug/p/:itemId" element={<PublicShop />} />
          <Route path="/home" element={<Guard><Home /></Guard>} />
          <Route path="/items" element={<Guard><Items /></Guard>} />
          <Route path="/videos" element={<Guard><Videos /></Guard>} />
          <Route path="/videos/:jobId" element={<Guard><VideoDetail /></Guard>} />
          <Route path="/record" element={<Guard><Record /></Guard>} />
          <Route path="/jobs/:jobId" element={<Guard><Processing /></Guard>} />
          <Route path="/jobs/:jobId/review" element={<Guard><Review /></Guard>} />
          <Route path="/settings" element={<Guard><Settings /></Guard>} />
          <Route path="/catalog" element={<Navigate to="/home" replace />} />
          <Route path="*" element={<Navigate to="/home" replace />} />
        </Routes>
      </SessionProvider>
    </BrowserRouter>
  );
}
