import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { TokenResponse } from '@/types';
import * as apiClient from '@/api/client';

interface AuthContextType {
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (usernamePasswordForm: URLSearchParams) => Promise<void>;
  logout: () => void;
  // user: User | null; // Optional: if you want to store user details
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(!!apiClient.getToken());
  const [isLoading, setIsLoading] = useState<boolean>(true);
  // const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    // Check token validity on initial load or fetch user profile
    const verifyAuth = async () => {
      const token = apiClient.getToken();
      if (token) {
        try {
          // Optional: Verify token by fetching user profile or a protected light endpoint
          // For now, just having a token means authenticated client-side
          // await apiClient.getCurrentUser(); // Example: if you have this endpoint
          setIsAuthenticated(true);
        } catch (error) {
          console.error("Token verification failed:", error);
          apiClient.removeToken();
          setIsAuthenticated(false);
        }
      } else {
        setIsAuthenticated(false);
      }
      setIsLoading(false);
    };
    verifyAuth();
  }, []);

  const login = async (usernamePasswordForm: URLSearchParams) => {
    setIsLoading(true);
    try {
      const tokenResponse: TokenResponse = await apiClient.login(usernamePasswordForm);
      apiClient.storeToken(tokenResponse.access_token);
      setIsAuthenticated(true);
      // const currentUser = await apiClient.getCurrentUser(); // Fetch user after login
      // setUser(currentUser);
    } catch (error) {
      console.error("Login failed:", error);
      setIsAuthenticated(false);
      // setUser(null);
      throw error; // Re-throw to allow component to handle UI error
    } finally {
      setIsLoading(false);
    }
  };

  const logout = () => {
    apiClient.logout(); // This removes the token from apiClient
    setIsAuthenticated(false);
    // setUser(null);
    // Optionally redirect to login page or home
  };

  return (
    <AuthContext.Provider value={{ isAuthenticated, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};