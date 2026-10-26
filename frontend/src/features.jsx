// Optional parts of the portal, as switched on by the server (GET /api/health -> features).
// The Warehouse tab only exists while the warehouse is switched on (start file or admin switch).
import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api } from './api'

const FeaturesContext = createContext({ loaded: false, warehouse: false, setWarehouse: async () => {} })

export function FeaturesProvider({ children }) {
  const [features, setFeatures] = useState({ loaded: false, warehouse: false })
  useEffect(() => {
    api('/health')
      .then((h) => setFeatures({ loaded: true, warehouse: !!h.features?.warehouse }))
      .catch(() => setFeatures({ loaded: true, warehouse: false }))
  }, [])
  // admin only: flips the switch on the server, then updates the menu immediately
  const setWarehouse = useCallback(async (on) => {
    const r = await api('/admin/features', { method: 'POST', body: { warehouse: on } })
    setFeatures({ loaded: true, warehouse: !!r.features.warehouse })
  }, [])
  return <FeaturesContext.Provider value={{ ...features, setWarehouse }}>{children}</FeaturesContext.Provider>
}

export const useFeatures = () => useContext(FeaturesContext)
