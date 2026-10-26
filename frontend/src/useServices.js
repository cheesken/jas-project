import { useEffect, useState } from 'react';

export const canManageServices = () => Boolean(window.electronAPI?.getServices);

export const STARTING = ['checking', 'starting', 'first-run', 'waiting'];

export function useServices() {
  const [state, setState] = useState(null);
  useEffect(() => {
    if (!canManageServices()) return undefined;
    let active = true;
    window.electronAPI.getServices().then((s) => active && setState(s));
    const off = window.electronAPI.onServicesUpdate(setState);
    return () => {
      active = false;
      off();
    };
  }, []);
  return state;
}
