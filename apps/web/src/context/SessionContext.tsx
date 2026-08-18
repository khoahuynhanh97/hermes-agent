import React, { createContext, useContext, useState, useEffect } from 'react'

export interface ServerPrincipal {
  actor_id: string
  owner_user_id: string
  platform: string
  session_id: string
  roles: string[]
}

interface SessionContextType {
  authenticated: boolean
  ownerUserId: string | null
  principal: ServerPrincipal | null
  isLoading: boolean
  error: string | null
  refetchSession: () => Promise<void>
}

const SessionContext = createContext<SessionContextType>({
  authenticated: false,
  ownerUserId: null,
  principal: null,
  isLoading: true,
  error: null,
  refetchSession: async () => {},
})

export const SessionProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [authenticated, setAuthenticated] = useState<boolean>(false)
  const [ownerUserId, setOwnerUserId] = useState<string | null>(null)
  const [principal, setPrincipal] = useState<ServerPrincipal | null>(null)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  const fetchServerSession = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const res = await fetch('http://127.0.0.1:8000/api/session', {
        headers: { Accept: 'application/json' },
      })
      if (!res.ok) {
        throw new Error(`Server returned HTTP ${res.status}: Unauthenticated`)
      }
      const data = await res.json()
      if (data?.status === 'ok' && data?.principal?.owner_user_id) {
        setAuthenticated(true)
        setOwnerUserId(data.principal.owner_user_id)
        setPrincipal(data.principal)
      } else {
        throw new Error('Invalid session payload')
      }
    } catch (err: any) {
      setAuthenticated(false)
      setOwnerUserId(null)
      setPrincipal(null)
      setError(err.message || 'Unauthenticated server session')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchServerSession()
  }, [])

  return (
    <SessionContext.Provider
      value={{
        authenticated,
        ownerUserId,
        principal,
        isLoading,
        error,
        refetchSession: fetchServerSession,
      }}
    >
      {children}
    </SessionContext.Provider>
  )
}

export const useSession = () => useContext(SessionContext)
