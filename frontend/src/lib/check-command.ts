import { api } from './api';
import { CheckKeys } from './check-keys';
import type { Check } from './types';

const keys = new CheckKeys();
export async function verify(workspace: string, monitor: string): Promise<Check> {
  const key = keys.getOrCreate(workspace, monitor);
  const result = await api.write<Check>(`/api/monitors/${monitor}/checks`, { key }, workspace);
  keys.observe(workspace, monitor, result.state);
  return result;
}
