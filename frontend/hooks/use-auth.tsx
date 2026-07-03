"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import { loginUser, signupUser, fetchDashboardStats } from "../services/auth";
import { DashboardUserStats } from "../types/auth";
import { clearSession, getCurrentUser, getToken, setSession } from "../src/lib/auth";

interface AuthContextType {
  user: DashboardUserStats | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (credentials: any) => Promise<void>;
  signup: (userData: any) => Promise<void>;
  logout: () => void;
  refreshSession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);
const SESSION_EXPIRED_EVENT = "auth:session-expired";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<DashboardUserStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();

  const refreshSession = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setUser(null);
      setIsLoading(false);
      return;
    }

    const storedUser = getCurrentUser();
    if (storedUser) {
      setUser(storedUser);
    }
    
    try {
      setIsLoading(true);
      const data = await fetchDashboardStats();
      setUser(data.user);
      const activeToken = getToken();
      if (activeToken) {
        setSession({ access_token: activeToken, user: data.user });
      }
    } catch (error) {
      console.error("Failed to verify session token", error);
      if (!getToken()) {
        setUser(null);
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshSession();
  }, [refreshSession]);

  useEffect(() => {
    const handleSessionExpired = () => {
      clearSession();
      setUser(null);
      setIsLoading(false);
      router.replace("/login");
    };

    window.addEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);
    return () => {
      window.removeEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);
    };
  }, [router]);

  const login = async (credentials: any) => {
    setIsLoading(true);
    try {
      const response = await loginUser(credentials);
      setSession({
        access_token: response.access_token,
        refresh_token: response.refresh_token,
        user: response.user,
      });
      setUser(response.user);
      setIsLoading(false);
      router.push("/dashboard");

      try {
        const data = await fetchDashboardStats();
        setUser(data.user);
        setSession({
          access_token: response.access_token,
          refresh_token: response.refresh_token,
          user: data.user,
        });
      } catch (verificationError) {
        console.error("Login succeeded, but dashboard verification failed", verificationError);
      }
    } catch (error) {
      setIsLoading(false);
      throw error;
    }
  };

  const signup = async (userData: any) => {
    setIsLoading(true);
    try {
      await signupUser(userData);
      setIsLoading(false);
    } catch (error) {
      setIsLoading(false);
      throw error;
    }
  };

  const logout = () => {
    clearSession();
    setUser(null);
    router.push("/login");
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        signup,
        logout,
        refreshSession,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
