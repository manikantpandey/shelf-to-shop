import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { api, ApiError, setCsrf, type Me } from "./api";
import { setLanguage } from "./i18n";

type SessionState = {
  me: Me | null;
  loading: boolean;
  refresh: () => Promise<Me | null>;
  setMe: (me: Me | null) => void;
};

const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMeState] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const setMe = useCallback((next: Me | null) => {
    setMeState(next);
    setCsrf(next?.csrf_token);
    if (next) setLanguage(next.workspace.language);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const data = await api<Me>("/api/v1/me");
      setMe(data);
      return data;
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setMe(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, [setMe]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return <SessionContext.Provider value={{ me, loading, refresh, setMe }}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionState {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession outside SessionProvider");
  return value;
}
