import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, clearTokens, getToken, setTokens, type User } from './api'

interface AuthState {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthCtx = createContext<AuthState>(null as unknown as AuthState)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    ;(async () => {
      if (getToken()) {
        try {
          setUser(await api.get<User>('/auth/me'))
        } catch {
          clearTokens()
        }
      }
      setLoading(false)
    })()
  }, [])

  const login = async (username: string, password: string) => {
    const t = await api.login(username, password)
    setTokens(t.access_token, t.refresh_token)
    setUser(await api.get<User>('/auth/me'))
  }
  const logout = () => {
    clearTokens()
    setUser(null)
  }

  return <AuthCtx.Provider value={{ user, loading, login, logout }}>{children}</AuthCtx.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => useContext(AuthCtx)
