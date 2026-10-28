import { lazy, Suspense, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { Home } from "./screens/Home";
import { Items } from "./screens/Items";
import { Landing } from "./screens/Landing";
import { More } from "./screens/More";
import { Orders } from "./screens/Orders";
import { Processing } from "./screens/Processing";
import { PublicShop } from "./screens/PublicShop";
import { Record } from "./screens/Record";
import { Review } from "./screens/Review";
import { Sections } from "./screens/Sections";
import { Settings } from "./screens/Settings";
import { Setup } from "./screens/Setup";
import { ShopProfile } from "./screens/ShopProfile";
import { SignIn } from "./screens/SignIn";
import { VideoDetail } from "./screens/VideoDetail";
import { Videos } from "./screens/Videos";
import { SessionProvider, useSession } from "./session";

// The share kit and poster carry the QR library; customers on the shop page never download it.
const Share = lazy(() => import("./screens/Share").then((m) => ({ default: m.Share })));
const Poster = lazy(() => import("./screens/Poster").then((m) => ({ default: m.Poster })));

function Guard({ children }: { children: ReactElement }) {
  const { me, loading } = useSession();
  const { t } = useTranslation();
  if (loading) return <p className="content muted">{t("app.loading")}</p>;
  if (!me) return <Navigate to="/signin" replace />;
  if (!me.workspace.consent_account || !me.workspace.whatsapp) return <Navigate to="/setup" replace />;
  return <Suspense fallback={<p className="content muted">{t("app.loading")}</p>}>{children}</Suspense>;
}

const SELLER: [string, ReactElement][] = [
  ["/home", <Home />],
  ["/orders", <Orders />],
  ["/items", <Items />],
  ["/videos", <Videos />],
  ["/videos/:jobId", <VideoDetail />],
  ["/record", <Record />],
  ["/jobs/:jobId", <Processing />],
  ["/jobs/:jobId/review", <Review />],
  ["/shop", <ShopProfile />],
  ["/sections", <Sections />],
  ["/share", <Share />],
  ["/poster", <Poster />],
  ["/more", <More />],
  ["/settings", <Settings />],
];

export function App() {
  return (
    <BrowserRouter>
      <SessionProvider>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/signin" element={<SignIn />} />
          <Route path="/setup" element={<Setup />} />
          <Route path="/s/:slug" element={<PublicShop />} />
          <Route path="/s/:slug/p/:itemId" element={<PublicShop />} />
          {SELLER.map(([path, element]) => (
            <Route key={path} path={path} element={<Guard>{element}</Guard>} />
          ))}
          <Route path="/catalog" element={<Navigate to="/home" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </SessionProvider>
    </BrowserRouter>
  );
}
