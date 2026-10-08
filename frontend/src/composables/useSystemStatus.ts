import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'

import { fetchSystemStatus } from '@/api/system'
import { summarizeSystemHealth } from '@/lib/systemHealth'

const REFRESH_INTERVAL_MS = 5_000

export function useSystemStatus() {
  const query = useQuery({
    queryKey: ['system', 'status'],
    queryFn: ({ signal }) => fetchSystemStatus(signal),
    refetchInterval: REFRESH_INTERVAL_MS,
    retry: false,
  })
  const level = computed(() => summarizeSystemHealth(query.data.value, query.isError.value))
  return { ...query, level }
}
