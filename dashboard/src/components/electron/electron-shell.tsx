import { useEffect, useState } from 'react'

import { BackendSetupWizard } from './BackendSetupWizard'

export function ElectronShell() {
  const [isFirstLaunch, setIsFirstLaunch] = useState(false)

  useEffect(() => {
    window.electronAPI!.isFirstLaunch().then(setIsFirstLaunch)
  }, [])

  const isAmadeusWorkspace =
    window.location.pathname === '/' || window.location.pathname.startsWith('/amadeus')
  return <BackendSetupWizard open={isFirstLaunch && !isAmadeusWorkspace} />
}
