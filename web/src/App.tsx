import type { ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { Catalog } from "./screens/Catalog";
import { Processing } from "./screens/Processing";
import { PublicShop } from "./screens/PublicShop";
import { Record } from "./screens/Record";
import { Review } from "./screens/Review";
import { Settings } from "./screens/Settings";
import { Setup } from "./screens/Setup";
import { SignIn } from "./screens/SignIn";
import { SessionProvider, useSession } from "./session";

function Guard({ children }: { children: ReactElement }) {
  const { me, loading } = useSession();
  const { t } = useTranslation();
  if (loading) return <p className="body">{t("app.loading")}</p>;
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
          <Route path="/record" element={<Guard><Record /></Guard>} />
          <Route path="/jobs/:jobId" element={<Guard><Processing /></Guard>} />
          <Route path="/jobs/:jobId/review" element={<Guard><Review /></Guard>} />
          <Route path="/catalog" element={<Guard><Catalog /></Guard>} />
          <Route path="/settings" element={<Guard><Settings /></Guard>} />
          <Route path="*" element={<Navigate to="/record" replace />} />
        </Routes>
      </SessionProvider>
    </BrowserRouter>
  );
}
